Option Explicit

Dim fso, shell, repoDir, batchPath, command
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

repoDir = fso.GetParentFolderName(WScript.ScriptFullName)
batchPath = fso.BuildPath(repoDir, "run_clipai.bat")

shell.CurrentDirectory = repoDir
command = """" & batchPath & """"
shell.Run command, 0, False
