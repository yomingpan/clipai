Option Explicit

Dim fso, shell, repoDir, pythonwPath, markerPath, mainPath, batchPath, logDir, startupLog, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

repoDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonwPath = fso.BuildPath(repoDir, ".venv\Scripts\pythonw.exe")
markerPath = fso.BuildPath(repoDir, ".venv\.clipai-bootstrap")
mainPath = fso.BuildPath(repoDir, "main.py")
batchPath = fso.BuildPath(repoDir, "run_clipai.bat")
logDir = fso.BuildPath(repoDir, "logs")
startupLog = fso.BuildPath(logDir, "startup.log")

If Not fso.FolderExists(logDir) Then
    fso.CreateFolder(logDir)
End If

If Not fso.FileExists(pythonwPath) Or Not fso.FileExists(markerPath) Then
    With fso.OpenTextFile(startupLog, 8, True)
        .WriteLine Now & " [clipai] Starting first-use environment setup."
        .Close
    End With
    shell.CurrentDirectory = repoDir
    command = """" & batchPath & """"
    shell.Run command, 1, False
    WScript.Quit 0
End If

shell.CurrentDirectory = repoDir
command = """" & pythonwPath & """ """ & mainPath & """"
shell.Run command, 0, False
