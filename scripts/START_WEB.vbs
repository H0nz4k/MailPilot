Option Explicit
Dim shell, files, directory, executable, result
Set shell = CreateObject("WScript.Shell")
Set files = CreateObject("Scripting.FileSystemObject")
directory = files.GetParentFolderName(WScript.ScriptFullName)
executable = files.BuildPath(directory, "DataShip.exe")
If Not files.FileExists(executable) Then
    MsgBox "DataShip.exe nebyl nalezen. Spoustec START_WEB.vbs musi byt vedle DataShip.exe.", vbCritical, "DataShip"
    WScript.Quit 2
End If
shell.CurrentDirectory = directory
On Error Resume Next
result = shell.Run(Chr(34) & executable & Chr(34) & " --browser", 0, False)
If Err.Number <> 0 Then
    MsgBox "DataShip nelze spustit. Pro podrobnosti pouzijte START_WEB_DEBUG.cmd.", vbCritical, "DataShip"
    WScript.Quit 2
End If
On Error GoTo 0
