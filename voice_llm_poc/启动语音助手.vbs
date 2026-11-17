' 语音助手 - 静默启动(托盘常驻,无黑窗)
' 双击本文件即可启动,程序以托盘图标形式运行,不弹任何窗口。
Option Explicit
Dim fso, sh, dir, pyw, cmd
Set fso = CreateObject("Scripting.FileSystemObject")
Set sh  = CreateObject("WScript.Shell")
dir = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = dir

' 选 pythonw(无控制台的 python):优先本目录 venv,否则系统
pyw = "pythonw"
If fso.FileExists(dir & "\venv\Scripts\pythonw.exe") Then
    pyw = """" & dir & "\venv\Scripts\pythonw.exe"""
ElseIf fso.FileExists(dir & "\.venv\Scripts\pythonw.exe") Then
    pyw = """" & dir & "\.venv\Scripts\pythonw.exe"""
End If

cmd = pyw & " main.py --tray"
' 0 = 隐藏窗口, False = 不等待
sh.Run cmd, 0, False
