Option Explicit

Dim fso, shell, repoDir, pythonwPath, mainPath, logDir, startupLog, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

repoDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonwPath = fso.BuildPath(repoDir, ".venv\Scripts\pythonw.exe")
mainPath = fso.BuildPath(repoDir, "main.py")
logDir = fso.BuildPath(repoDir, "logs")
startupLog = fso.BuildPath(logDir, "startup.log")

If Not fso.FolderExists(logDir) Then
    fso.CreateFolder(logDir)
End If

If Not fso.FileExists(pythonwPath) Then
    With fso.OpenTextFile(startupLog, 8, True)
        .WriteLine Now & " [clipai] Missing launcher dependency: " & pythonwPath
        .Close
    End With
    MsgBox "ClipAI virtual environment was not found. Please use run_clipai.bat for setup/debug.", vbExclamation, "ClipAI"
    WScript.Quit 1
End If

shell.CurrentDirectory = repoDir
command = """" & pythonwPath & """ """ & mainPath & """"
shell.Run command, 0, False
