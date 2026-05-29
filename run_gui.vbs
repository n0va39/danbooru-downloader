Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

appDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = fso.BuildPath(appDir, ".venv\Scripts\pythonw.exe")
mainPy = fso.BuildPath(appDir, "main.py")

If Not fso.FileExists(pythonw) Then
    MsgBox "pythonw.exe not found: " & pythonw, vbCritical, "Danbooru Downloader"
    WScript.Quit 1
End If

If Not fso.FileExists(mainPy) Then
    MsgBox "main.py not found: " & mainPy, vbCritical, "Danbooru Downloader"
    WScript.Quit 1
End If

shell.CurrentDirectory = appDir
shell.Run """" & pythonw & """ """ & mainPy & """", 0, False
