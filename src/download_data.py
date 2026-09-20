"""Pinned, public data from the authors. Never replaces the user's connections.csv."""
from pathlib import Path
import hashlib
import json
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
SOURCES = {
    'Connectivity_783.parquet': 'https://raw.githubusercontent.com/philshiu/Drosophila_brain_model/91bdd1e7dcf193f3e7ca5a8933497fcef63b7960/Connectivity_783.parquet',
    'Completeness_783.csv': 'https://raw.githubusercontent.com/philshiu/Drosophila_brain_model/91bdd1e7dcf193f3e7ca5a8933497fcef63b7960/Completeness_783.csv',
    'annotations.tsv': 'https://raw.githubusercontent.com/flyconnectome/flywire_annotations/8587524c1748ce5ef2080822a2fc890fc03bf597/supplemental_files/Supplemental_file1_neuron_annotations.tsv',
}

def main():
    folder = ROOT / 'data' / 'raw'
    folder.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, url in SOURCES.items():
        dest = folder / name
        if not dest.exists():
            print('Downloading', name, flush=True)
            req = urllib.request.Request(url, headers={'User-Agent': 'Fly-UCN-local-research/1.0'})
            with urllib.request.urlopen(req, timeout=90) as response, dest.with_suffix(dest.suffix + '.part').open('wb') as out:
                while block := response.read(1024 * 1024):
                    out.write(block)
            dest.with_suffix(dest.suffix + '.part').replace(dest)
        digest = hashlib.sha256(dest.read_bytes()).hexdigest()
        manifest[name] = {'url': url, 'bytes': dest.stat().st_size, 'sha256': digest}
        print(name, manifest[name], flush=True)
    (folder / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')

if __name__ == '__main__':
    main()
