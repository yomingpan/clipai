#ifndef StageRoot
  #error StageRoot required
#endif
#ifndef OutputRoot
  #error OutputRoot required
#endif
#ifndef AppVersion
  #error AppVersion required
#endif

// Shared thin wizard. Preview defaults remain isolated.
#ifndef ProductName
  #define ProductName "ClipAI Preview"
#endif
#ifndef ProductId
  #define ProductId "ClipAI.LocalAcceptance.Preview"
#endif
#ifndef OutputName
  #define OutputName "ClipAI-Preview-" + AppVersion + "-Setup"
#endif
#ifndef WelcomeText
  #define WelcomeText "Local acceptance candidate. This Setup is unsigned and is not an official release."
#endif

[Setup]
AppId={#ProductId}
AppName={#ProductName}
AppVersion={#AppVersion}
AppPublisher=ClipAI
SetupIconFile={#StageRoot}\setup-engine\clipai.ico
DefaultDirName={localappdata}\Programs\{#ProductName}
PrivilegesRequired=lowest
ArchitecturesAllowed=x64os
DisableDirPage=yes
DisableProgramGroupPage=yes
CreateAppDir=no
Uninstallable=no
OutputDir={#OutputRoot}
OutputBaseFilename={#OutputName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
MinVersion=10.0.22000
SetupLogging=yes
CloseApplications=no
RestartApplications=no
DisableWelcomePage=no

[Files]
Source: "{#StageRoot}\*"; DestDir: "{tmp}\clipai-preview"; Flags: recursesubdirs createallsubdirs deleteafterinstall

[Run]
Filename: "{localappdata}\Programs\{#ProductName}\runtime\pythonw.exe"; Parameters: "-I ""{localappdata}\Programs\{#ProductName}\setup-engine\entry.py"" launch --install-root ""{localappdata}\Programs\{#ProductName}"" --shared-root ""{localappdata}\{#ProductName}"""; Description: "Launch {#ProductName}"; Flags: postinstall unchecked skipifsilent; Check: CanLaunch

[Code]
var
  ActionPage: TInputOptionWizardPage;
  LastPhase: String;
  EngineRunning: Boolean;
  OperationExitCode: Integer;

function GetCustomSetupExitCode: Integer;
begin
  Result := OperationExitCode;
end;

procedure CancelButtonClick(CurPageID: Integer; var Cancel, Confirm: Boolean);
begin
  if EngineRunning then begin
    Cancel := False;
    Confirm := False;
    if (Pos('checking', LastPhase) > 0) or (Pos('preparing', LastPhase) > 0) then begin
      SaveStringToFile(ExpandConstant('{tmp}\clipai-preview\cancel.request'), 'cancel', False);
      WizardForm.CancelButton.Enabled := False;
      WizardForm.StatusLabel.Caption := 'Cancellation requested. Waiting for owned work to settle...';
    end;
  end;
end;

function IsInstallAction: Boolean;
begin
  Result := ActionPage.SelectedValueIndex = 0;
end;

function CanLaunch: Boolean;
begin
  Result := IsInstallAction and (OperationExitCode = 0) and
    (ExpandConstant('{param:VERIFYONLY|0}') <> '1');
end;

procedure ShowOperationResult;
var
  Detail: String;
begin
  if ExpandConstant('{param:VERIFYONLY|0}') = '1' then begin
    WizardForm.RunList.Visible := False;
    if OperationExitCode = 0 then begin
      WizardForm.FinishedHeadingLabel.Caption := 'Payload verification completed';
      WizardForm.FinishedLabel.Caption := 'The packaged bundle identity was verified. No application was installed or removed.';
    end else begin
      WizardForm.FinishedHeadingLabel.Caption := 'Payload verification failed';
      WizardForm.FinishedLabel.Caption := 'The packaged payload could not be verified. No application was installed or removed.';
    end;
    Exit;
  end;
  if OperationExitCode <> 0 then begin
    if IsInstallAction then WizardForm.FinishedHeadingLabel.Caption := 'Installation did not complete'
    else WizardForm.FinishedHeadingLabel.Caption := 'Removal did not complete';
    if Pos('InstallationBusyError', LastPhase) > 0 then
      Detail := 'ClipAI is still running. Choose Exit from the Tray, close ClipAI windows, then retry Remove.'
    else if IsInstallAction then
      Detail := 'Installation failed. Remove an existing installation first, then retry. See the Setup log for details.'
    else
      Detail := 'Removal failed. Close ClipAI and retry Remove. See the Setup log for details.';
    WizardForm.FinishedLabel.Caption := Detail + #13#10 + #13#10 +
      'Your settings and data have been retained. Finish closes this Setup; it does not mean the operation succeeded.';
    WizardForm.RunList.Visible := False;
  end else if IsInstallAction then begin
    WizardForm.FinishedHeadingLabel.Caption := '{#ProductName} installed';
    WizardForm.FinishedLabel.Caption := 'Open {#ProductName} from the desktop or Start Menu, or use Launch below. Configure your AI provider to obtain your first result.';
  end else begin
    WizardForm.FinishedHeadingLabel.Caption := '{#ProductName} removed';
    WizardForm.FinishedLabel.Caption := 'Program files, owned shortcuts and the uninstall entry have been removed.' + #13#10 + #13#10 +
      'Your API key, settings and data have been retained. You can reinstall using the same Setup.';
    WizardForm.RunList.Visible := False;
  end;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if CurPageID = wpReady then begin
    if not IsInstallAction then begin
      WizardForm.PageNameLabel.Caption := 'Ready to remove {#ProductName}';
      WizardForm.PageDescriptionLabel.Caption := 'Program files and owned shortcuts will be removed; settings and data will be retained.';
      WizardForm.ReadyMemo.Text := 'Close ClipAI from the Tray before continuing.' + #13#10 + #13#10 +
        'Remove {#ProductName} and retain data.';
      WizardForm.NextButton.Caption := '&Remove';
    end;
  end else if CurPageID = wpFinished then
    ShowOperationResult;
end;

procedure InitializeWizard;
begin
  OperationExitCode := 100;
  WizardForm.WelcomeLabel2.Caption :=
    '{#WelcomeText}' + #13#10 + #13#10 +
    'Includes offline Python and dependencies. Uses separate {#ProductName} folders.' + #13#10 +
    'Provider credentials and internet are required only when you configure and use AI.';
  ActionPage := CreateInputOptionPage(wpWelcome, 'Choose operation',
    'Install or remove {#ProductName}',
    'Close ClipAI before removing it. API keys, preferences and data are retained.', True, False);
  ActionPage.Add('Install {#ProductName}');
  ActionPage.Add('Remove {#ProductName} and retain data');
  ActionPage.SelectedValueIndex := 0;
  if ExpandConstant('{param:REMOVE|0}') = '1' then
    ActionPage.SelectedValueIndex := 1;
end;

procedure EngineOutput(const S: String; const Error, FirstLine: Boolean);
begin
  if (not Error) and (Pos('CLIPAI_PHASE:', S) = 1) then begin
    LastPhase := S;
    Log(S);
    if Pos('checking', S) > 0 then WizardForm.StatusLabel.Caption := 'Checking installation...'
    else if Pos('preparing', S) > 0 then WizardForm.StatusLabel.Caption := 'Verifying bundle and building offline environments...'
    else if Pos('committing', S) > 0 then WizardForm.StatusLabel.Caption := 'Committing installation...'
    else if Pos('integrating', S) > 0 then WizardForm.StatusLabel.Caption := 'Creating Start Menu and uninstall entries...'
    else if Pos('installed_integration_incomplete', S) > 0 then
      WizardForm.StatusLabel.Caption := 'Program files installed; Windows integration did not complete.'
    else if Pos('uninstalled', S) > 0 then WizardForm.StatusLabel.Caption := 'Removal completed. Data retained.'
    else if Pos('installed', S) > 0 then WizardForm.StatusLabel.Caption := 'Installation completed.'
    else if Pos('cancelled', S) > 0 then WizardForm.StatusLabel.Caption := 'Cancelled. Owned work has settled.'
    else if Pos('removing', S) > 0 then WizardForm.StatusLabel.Caption := 'Removing program files; retaining settings and data...'
    else WizardForm.StatusLabel.Caption := 'Operation did not complete. See the Setup log for details.';
    if (Pos('committing', S) > 0) or (Pos('integrating', S) > 0) then
      WizardForm.CancelButton.Enabled := False;
    WizardForm.StatusLabel.Update;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  Engine, Params, Action: String;
  ExitCode: Integer;
begin
  if CurStep = ssPostInstall then begin
    // Prove the bytes actually extracted from the compiled Setup before any
    // installation side effect. Preview keeps its original runtime admission.
#ifdef BundleSha256
    if (GetSHA256OfFile(ExpandConstant('{tmp}\clipai-preview\bundle.zip')) <> '{#BundleSha256}') or
       (GetSHA256OfFile(ExpandConstant('{tmp}\clipai-preview\setup-engine\managed-update-trusted-keys.json')) <> '{#KeyringSha256}') then begin
      Log('CLIPAI_SETUP_RESULT:identity_mismatch');
      OperationExitCode := 100;
      Exit;
    end;
    if ExpandConstant('{param:VERIFYONLY|0}') = '1' then begin
      OperationExitCode := 0;
      Log('CLIPAI_SETUP_RESULT:verified_payload:{#BundleSha256}');
      SaveStringToFile(ExpandConstant('{param:VERIFICATIONOUTPUT|}'), '{#BundleSha256}', False);
      Exit;
    end;
#else
    if ExpandConstant('{param:VERIFYONLY|0}') = '1' then begin
      OperationExitCode := 100;
      Log('CLIPAI_SETUP_RESULT:verification_unavailable');
      Exit;
    end;
#endif
    EngineRunning := True;
    WizardForm.CancelButton.Enabled := IsInstallAction;
    WizardForm.ProgressGauge.Visible := False;
    WizardForm.StatusLabel.Caption := 'Working. Environment creation can take a few minutes...';
    Engine := ExpandConstant('{tmp}\clipai-preview\runtime\python.exe');
    if IsInstallAction then Action := 'install' else Action := 'remove-worker';
    Params := '-I "' + ExpandConstant('{tmp}\clipai-preview\setup-engine\entry.py') + '" ' + Action +
      ' --quiet --install-root "' + ExpandConstant('{localappdata}\Programs\{#ProductName}') +
      '" --shared-root "' + ExpandConstant('{localappdata}\{#ProductName}') +
      '" --cancel-intent "' + ExpandConstant('{tmp}\clipai-preview\cancel.request') + '"';
    ExitCode := 100;
    if not ExecAndLogOutput(Engine, Params, '', SW_SHOWNORMAL, ewWaitUntilTerminated, ExitCode, @EngineOutput) then
      ExitCode := 100;
    EngineRunning := False;
    if ExitCode <> 0 then begin
      OperationExitCode := 100;
      Log('CLIPAI_SETUP_RESULT:failed');
      Exit;
    end;
    OperationExitCode := 0;
    Log('CLIPAI_SETUP_RESULT:success');
  end;
  // Inno fills its stock completion text after ssPostInstall. Render only
  // after that boundary; ssDone also covers silent Setup runs.
  if CurStep = ssDone then ShowOperationResult;
end;
