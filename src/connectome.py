"""Full FlyWire v783 topology, simplified leaky-rate reservoir (not a biological replica)."""
from pathlib import Path
import hashlib
import json
import numpy as np
import pandas as pd
from scipy import sparse

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / 'data' / 'cache'

def prepare():
    CACHE.mkdir(parents=True, exist_ok=True)
    raw = ROOT / 'data' / 'raw'
    ids = pd.read_csv(raw / 'Completeness_783.csv').iloc[:, 0].to_numpy(np.int64)
    if len(np.unique(ids)) != len(ids):
        raise ValueError('Duplicate neuron IDs')
    df = pd.read_parquet(raw / 'Connectivity_783.parquet', columns=[
        'Presynaptic_ID', 'Postsynaptic_ID', 'Presynaptic_Index', 'Postsynaptic_Index',
        'Connectivity', 'Excitatory x Connectivity'])
    pre = df['Presynaptic_Index'].to_numpy(np.int32)
    post = df['Postsynaptic_Index'].to_numpy(np.int32)
    if not (np.array_equal(ids[pre], df.Presynaptic_ID) and np.array_equal(ids[post], df.Postsynaptic_ID)):
        raise ValueError('Index / root ID mismatch; refusing incompatible data')
    # Aggregate all published rows. No invented edges, no subset of neurons.
    weights = sparse.coo_matrix((df['Excitatory x Connectivity'].to_numpy(np.float32),
                                 (post, pre)), shape=(len(ids), len(ids))).tocsr()
    weights.eliminate_zeros()
    edge_count = weights.nnz
    # Absolute incoming normalization bounds the recurrent drive and prevents blow-up.
    incoming = np.asarray(abs(weights).sum(axis=1)).ravel()
    weights = (sparse.diags(0.92 / np.maximum(incoming, 1)) @ weights).tocsr()
    sparse.save_npz(CACHE / 'weights.npz', weights)

    anno = pd.read_csv(raw / 'annotations.tsv', sep='\t', low_memory=False).drop_duplicates('root_id').set_index('root_id').reindex(ids)
    soma = anno[['soma_x', 'soma_y', 'soma_z']].to_numpy(np.float64)
    pos = anno[['pos_x', 'pos_y', 'pos_z']].to_numpy(np.float64)
    soma_valid = np.isfinite(soma).all(axis=1)
    coords = np.where(soma_valid[:, None], soma, pos)
    valid = np.isfinite(coords).all(axis=1)
    # FAFB coordinates are voxels of 4 x 4 x 40 nm. Use one physical scale for all axes.
    coords *= np.array([4, 4, 40])
    center = np.nanmedian(coords[valid], axis=0)
    scale = np.max(np.nanpercentile(coords[valid], 99, axis=0) - np.nanpercentile(coords[valid], 1, axis=0)) / 2
    coords = ((coords - center) / scale).astype(np.float32)
    coords[:, 1:] *= -1
    classes = anno.super_class.fillna('unknown').to_numpy(str)
    labels, groups = np.unique(classes, return_inverse=True)
    nt = anno.top_nt.fillna('unknown').to_numpy(str)
    types = anno.cell_type.fillna('').to_numpy(str)
    rng = np.random.default_rng(783)
    visual = np.flatnonzero(np.isin(classes, ['optic', 'visual_projection']))
    sensors = rng.choice(visual, min(len(visual), 12000), replace=False)
    # Engineered screen encoder: 32x18 luminance and frame difference. This mapping
    # is artificial, NOT a claim that FlyWire soma positions define visual receptive fields.
    channels = rng.integers(0, 1152, len(sensors), dtype=np.int32)
    polarity = rng.choice(np.array([-1, 1], np.float32), len(sensors))
    readout = []
    for name in labels:
        ix = np.flatnonzero(classes == name)
        count = min(len(ix), 96 if name in ['central', 'descending', 'visual_projection', 'optic'] else 24)
        readout.extend(rng.choice(ix, count, replace=False).tolist())
    readout = np.array(readout, np.int32)
    shown = rng.choice(np.flatnonzero(valid), min(valid.sum(), 5000), replace=False)
    # Keep visible edges sparse; full graph still participates in every simulation step.
    sub = abs(weights[shown][:, shown]).tocoo()
    strongest = np.argsort(sub.data)[-1400:]
    view_edges = np.column_stack([sub.col[strongest], sub.row[strongest]]).tolist()
    np.savez_compressed(CACHE / 'neurons.npz', ids=ids, coords=coords, valid=valid,
        groups=groups.astype(np.int16), labels=labels, classes=classes, nt=nt, types=types,
        sensors=sensors, channels=channels, polarity=polarity, readout=readout, shown=shown)
    manifest = json.loads((raw / 'manifest.json').read_text(encoding='utf-8'))
    signature = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    meta = dict(version='FAFB v783 / Shiu data', neurons=len(ids), edges=int(edge_count),
        synapses=int(df.Connectivity.sum()), shown=len(shown), coordinate_count=int(valid.sum()),
        soma_count=int(soma_valid.sum()), feature_count=len(readout) + len(labels) + 1,
        model='Leaky-rate reservoir, signed FlyWire graph; trained artificial readout',
        signature=signature, view_edges=view_edges, sources=manifest)
    (CACHE / 'metadata.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in meta.items() if k not in ['sources','view_edges']}, indent=2), flush=True)

class Brain:
    def __init__(self):
        if not (CACHE / 'metadata.json').exists():
            prepare()
        self.meta = json.loads((CACHE / 'metadata.json').read_text(encoding='utf-8'))
        self.w = sparse.load_npz(CACHE / 'weights.npz')
        with np.load(CACHE / 'neurons.npz', allow_pickle=False) as f:
            for name in f.files:
                setattr(self, name, f[name])
        self.state = np.zeros(len(self.ids), np.float32)
        self.previous = np.zeros(576, np.float32)
        self.group_sizes = np.bincount(self.groups)
        self.stimulation = None

    def reset(self):
        self.state.fill(0)
        self.previous.fill(0)

    def step(self, frame):
        pixels = np.asarray(frame.convert('L').resize((32,18)), np.float32).ravel() / 255
        signal = np.concatenate([pixels * 2 - 1, np.clip((pixels - self.previous) * 5, -1, 1)])
        self.previous = pixels
        drive = np.zeros_like(self.state)
        drive[self.sensors] = signal[self.channels] * self.polarity * 1.6
        if self.stimulation is not None:
            drive[self.stimulation] += 2
        for _ in range(2):
            self.state += .45 * (np.tanh(self.w @ self.state + drive) - self.state)
        means = np.bincount(self.groups, weights=self.state, minlength=len(self.labels)) / self.group_sizes
        features = np.concatenate([self.state[self.readout] * 3, means * 8, [1]]).astype(np.float32)
        return features

    def anatomy(self):
        ix = self.shown
        return dict(metadata={k:v for k,v in self.meta.items() if k!='view_edges'},
            ids=[str(x) for x in self.ids[ix]], xyz=self.coords[ix].round(5).tolist(),
            groups=self.groups[ix].tolist(), labels=self.labels.tolist(),
            types=self.types[ix].tolist(), nt=self.nt[ix].tolist(), edges=self.meta['view_edges'])

    def activity(self):
        return np.round(self.state[self.shown], 4).tolist()

if __name__ == '__main__':
    prepare()
