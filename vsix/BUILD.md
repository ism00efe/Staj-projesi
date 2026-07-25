# Building the Payment Assistant Visual Studio extension

> **This project has not been compiled.** It was authored on a machine with no Visual
> Studio IDE, no VS SDK, and no .NET SDK installed — only headless *Visual Studio Build
> Tools*, which cannot build a VSIX. Treat the first build as part of the review: expect
> to fix small compile errors, and read the [Known risks](#known-risks) section before
> starting.

## Prerequisites

1. **Visual Studio 2022 (17.x) or Visual Studio 2026 (18.x)** — the full IDE. Build Tools
   is not sufficient: a VSIX targets the IDE's extensibility host, which Build Tools does
   not contain.
2. The **"Visual Studio extension development"** workload. Install it from the Visual
   Studio Installer (*Modify* → *Workloads*). This is what supplies the VS SDK, the VSCT
   compiler, and the VSIX packaging targets.
3. The **.NET Framework 4.7.2 targeting pack** (included with the workload above).

## Build

```
git clone <this repo>
cd vsix
```

Open `PaymentAssistant.sln` in Visual Studio and build (Ctrl+Shift+B), or from a
*Developer Command Prompt*:

```
msbuild PaymentAssistant.sln /p:Configuration=Release /restore
```

The package lands at `PaymentAssistant/bin/Release/PaymentAssistant.vsix`.

## Debug

Press F5. This launches a second Visual Studio instance using the **Experimental**
hive (`/rootsuffix Exp`), so a broken build can never damage your day-to-day IDE. Reset
that hive at any time with:

```
"%VSSDKInstall%\VisualStudioIntegration\Tools\Bin\CreateExpInstance.exe" /Reset /VSInstance=17.0 /RootSuffix=Exp
```

## Install

Double-click the `.vsix`, or:

```
"%ProgramFiles%\Microsoft Visual Studio\2022\Community\Common7\IDE\VSIXInstaller.exe" PaymentAssistant.vsix
```

## Configure

**Tools → Options → Payment Assistant → General → API base URL.**
Default `http://127.0.0.1:7860`. This must point at a running Payment Assistant service
(see the repository README); the extension appends `/api/analyze`.

## What it does

| Where | Command | Behaviour |
|---|---|---|
| Editor context menu | *Analyze with Payment Assistant* | Sends the selected text. With no selection, and only for `.log`/`.json`/`.xml`, scans for `RC-\d{2}` / `ERR-\w+` / `errorCode` and opens a checkbox dialog — **only the ticked lines are sent**. |
| Solution Explorer context menu | *Analyze with Payment Assistant* | Visible only on `.log`/`.json`/`.xml`. Confirms first, then sends the whole file. |

Results appear in the **Payment Assistant** tool window (View → Other Windows if it is
closed). It is dockable and Visual Studio restores it across sessions.

### Data handling

No data is ever transmitted without an explicit user action — there is no file watching,
no background upload, and no implicit whole-file send. The no-selection path always routes
through the picker dialog; cancelling it sends nothing. Sensitive values are masked
server-side before the text reaches retrieval or the model.

## Known risks

Because the project has never been compiled, these are the places a first build is most
likely to complain. None require redesign — they are version-pinning and reference
details:

- **`Microsoft.VisualStudio.SDK` / `Microsoft.VSSDK.BuildTools` versions** in
  `PaymentAssistant.csproj` are pinned to known-good 17.x releases. If NuGet restore
  fails, update them to the latest 17.x available to you; the API surface used here
  (`AsyncPackage`, `ToolWindowPane`, `DialogPage`, `OleMenuCommand`, `DialogWindow`) has
  been stable across the whole 17.x line.
- **XAML assembly references.** Both XAML files reference
  `Microsoft.VisualStudio.Shell.15.0` for `VsBrushes` and `DialogWindow`. If the SDK
  package resolves those types from a differently-named assembly, fix the `assembly=`
  attribute in the two `xmlns:` declarations.
- **The tool-window dock target** in `PaymentAssistantPackage.cs` is the Output window's
  well-known GUID. If it does not resolve, drop the `Window = ...` argument entirely — the
  window then docks wherever the shell prefers, which is cosmetic only.
- **GUID consistency.** `PaymentAssistantPackage.CommandSetGuid`,
  `PaymentAssistantPackage.vsct`'s `guidPaymentAssistantCmdSet`, and the two
  `CommandId` constants must agree. If a menu item appears but does nothing, that pairing
  is where to look first.
- **CI does not build this.** The pipeline runs on `ubuntu-latest`, which cannot build a
  VSIX. Verification is manual until there is a Windows runner.

## Layout

```
PaymentAssistant/
  PaymentAssistantPackage.cs      AsyncPackage: registers commands, tool window, options
  PaymentAssistantPackage.vsct    command table — menu placement and captions
  Api/                            HTTP client + DTOs mirroring /api/analyze
  Commands/                       the two commands + their shared async runner
  Detection/ErrorCodeScanner.cs   error-code detection (no VS dependency — unit testable)
  Dialogs/                        checkbox picker for which lines to send
  Options/                        Tools > Options page
  ToolWindows/                    dockable result window (WPF)
```

`ErrorCodeScanner` is the only class with real logic and no shell dependency, which makes
it the one worth covering with unit tests once a test project exists.
