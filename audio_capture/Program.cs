// Windows process-loopback API. No endpoint-loopback or microphone fallback.
// https://learn.microsoft.com/en-us/samples/microsoft/windows-classic-samples/applicationloopbackaudio-sample/
using System.Diagnostics;
using System.Runtime.InteropServices;

[ComImport, Guid("72A22D78-CDE4-431D-B8CC-843A71199B6D"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IOperation { [PreserveSig] int GetActivateResult(out int hr, [MarshalAs(UnmanagedType.IUnknown)] out object result); }
[Guid("41D949AB-9862-444A-80F6-C261334DA5EB"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface ICompletion { [PreserveSig] int ActivateCompleted(IOperation operation); }
[Guid("94EA2B94-E9CC-49E0-C0FF-EE64CA8F5B90"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IAgileObject { }
[ComVisible(true), ClassInterface(ClassInterfaceType.None)]
public class Completion : ICompletion, IAgileObject {
    public ManualResetEventSlim Ready = new(); public object Result; public int Error;
    public int ActivateCompleted(IOperation op) {
        try { int hr = op.GetActivateResult(out Error, out Result); if(hr < 0) Error=hr; }
        catch(Exception e) { Error=e.HResult; }
        finally { Ready.Set(); } return 0;
    }
}
[StructLayout(LayoutKind.Sequential, Pack=2)]
struct WaveFormat { public ushort Tag, Channels; public uint Rate, Bytes; public ushort Align, Bits, Extra; }
[StructLayout(LayoutKind.Explicit, Size=24)]
struct Variant { [FieldOffset(0)] public ushort Type; [FieldOffset(8)] public uint Size; [FieldOffset(16)] public IntPtr Data; }
[ComImport, Guid("1CB9AD4C-DBFA-4c32-B178-C2F568A703B2"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface IAudioClient {
    [PreserveSig] int Initialize(int mode, uint flags, long duration, long period, ref WaveFormat format, IntPtr session);
    [PreserveSig] int GetBufferSize(out uint size);
    [PreserveSig] int GetStreamLatency(out long latency);
    [PreserveSig] int GetCurrentPadding(out uint padding);
    [PreserveSig] int IsFormatSupported(int mode, IntPtr format, out IntPtr closest);
    [PreserveSig] int GetMixFormat(out IntPtr format);
    [PreserveSig] int GetDevicePeriod(out long normal, out long minimum);
    [PreserveSig] int Start(); [PreserveSig] int Stop(); [PreserveSig] int Reset();
    [PreserveSig] int SetEventHandle(IntPtr handle);
    [PreserveSig] int GetService(ref Guid iid, [MarshalAs(UnmanagedType.IUnknown)] out object service);
}
[ComImport, Guid("C8ADBD64-E71E-48a0-A4DE-185C395CD317"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
interface ICapture {
    [PreserveSig] int GetBuffer(out IntPtr data, out uint frames, out uint flags, out ulong device, out ulong position);
    [PreserveSig] int ReleaseBuffer(uint frames);
    [PreserveSig] int GetNextPacketSize(out uint frames);
}
class Program {
    [DllImport("ole32.dll")] static extern int CoInitializeEx(IntPtr reserved, uint mode);
    [DllImport("ole32.dll")] static extern void CoUninitialize();
    [DllImport("Mmdevapi.dll", CharSet=CharSet.Unicode)]
    static extern int ActivateAudioInterfaceAsync(string path, ref Guid iid, ref Variant parameters,
        ICompletion callback, out IOperation operation);
    static void Check(int hr) { Marshal.ThrowExceptionForHR(hr); }
    [MTAThread] static int Main(string[] args) {
        IAudioClient client=null; ICapture capture=null; IntPtr blob=IntPtr.Zero;
        try {
            Check(CoInitializeEx(IntPtr.Zero,0));
            Console.OutputEncoding=System.Text.Encoding.UTF8;
            if(args.Length!=2) throw new ArgumentException("Expected game PID and exact executable path");
            using var game=Process.GetProcessById(int.Parse(args[0]));
            if(!string.Equals(Path.GetFullPath(game.MainModule.FileName),Path.GetFullPath(args[1]),StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("Target executable mismatch");
            blob=Marshal.AllocHGlobal(12);
            Marshal.WriteInt32(blob,0,1); // AUDIOCLIENT_ACTIVATION_TYPE_PROCESS_LOOPBACK
            Marshal.WriteInt32(blob,4,game.Id);
            Marshal.WriteInt32(blob,8,0); // INCLUDE_TARGET_PROCESS_TREE only
            var parameters=new Variant { Type=65, Size=12, Data=blob };
            var iid=typeof(IAudioClient).GUID; var completion=new Completion();
            Check(ActivateAudioInterfaceAsync("VAD\\Process_Loopback",ref iid,ref parameters,completion,out var operation));
            if(!completion.Ready.Wait(10000)) throw new TimeoutException("Audio activation timeout");
            Check(completion.Error); client=(IAudioClient)completion.Result;
            var format=new WaveFormat { Tag=1,Channels=2,Rate=48000,Bytes=192000,Align=4,Bits=16 };
            using var ready=new AutoResetEvent(false);
            Check(client.Initialize(0,0x20000|0x40000|0x80000000,200000,0,ref format,IntPtr.Zero));
            Check(client.SetEventHandle(ready.SafeWaitHandle.DangerousGetHandle()));
            var captureId=typeof(ICapture).GUID; Check(client.GetService(ref captureId,out var service)); capture=(ICapture)service;
            Check(client.Start());
            using var output=Console.OpenStandardOutput(); using var writer=new BinaryWriter(output);
            var stop=new CancellationTokenSource();
            _=Task.Run(()=> { Console.ReadLine(); stop.Cancel(); }); // EOF when parent exits
            Console.Error.WriteLine("Capturing UCN process tree only; stereo PCM16 48000 Hz");
            while(!stop.IsCancellationRequested && !game.HasExited) {
                if(!ready.WaitOne(250)) continue;
                Check(capture.GetNextPacketSize(out uint available));
                while(available>0) {
                    Check(capture.GetBuffer(out var data,out uint frames,out uint flags,out _,out _));
                    try {
                        var bytes=new byte[checked((int)frames*4)];
                        if((flags & 2)==0 && data!=IntPtr.Zero) Marshal.Copy(data,bytes,0,bytes.Length);
                        writer.Write(bytes.Length); writer.Write(bytes); writer.Flush();
                    } finally { Check(capture.ReleaseBuffer(frames)); }
                    Check(capture.GetNextPacketSize(out available));
                }
            }
            GC.KeepAlive(operation); GC.KeepAlive(completion); return 0;
        } catch(Exception e) { Console.Error.WriteLine(e.ToString()); return 1; }
        finally {
            if(client!=null) { client.Stop(); if(capture!=null) Marshal.ReleaseComObject(capture); Marshal.ReleaseComObject(client); }
            if(blob!=IntPtr.Zero) Marshal.FreeHGlobal(blob);
            CoUninitialize();
        }
    }
}

