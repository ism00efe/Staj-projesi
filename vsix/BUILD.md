# Building the Payment Assistant Visual Studio extension

**Status: builds clean.** Verified with *Visual Studio Build Tools 2026* (18.4) —
0 errors, 0 warnings, VSCT clean — producing a valid `PaymentAssistant.vsix` whose
`.pkgdef` registers the package, the command table, the tool window, and the
Tools→Options page.

> **Runtime behaviour is still unverified.** The build machine has no Visual Studio IDE
> (`devenv.exe` is absent), so the extension has never actually been *installed and run*.
> Menus appearing in the right place, the WPF tool window rendering, and the `DTE`
> selection interop are all compile-checked but not exercised. See
> [What is still unverified](#what-is-still-unverified).

## Prerequisites

Building does **not** require the full IDE — the VSSDK MSBuild targets ship with Build
Tools:

1. **Visual Studio Build Tools 2026 (18.x)** or the **Visual Studio 2022/2026 IDE**.
2. The **.NET Framework 4.7.2 targeting pack** (`C:\Program Files (x86)\Reference
   Assemblies\Microsoft\Framework\.NETFramework\v4.7.2`).
3. Network access for the first NuGet restore (`Microsoft.VisualStudio.SDK`,
   `Microsoft.VSSDK.BuildTools`).

**Installing and debugging** the result does require the IDE, with the *Visual Studio
extension development* workload.

## Build

From the repository root:

```
msbuild vsix/PaymentAssistant.sln /p:Configuration=Release /restore
```

Or with an explicit path to Build Tools' MSBuild:

```
"C:\Program Files (x86)\Microsoft Visual Studio\18\BuildTools\MSBuild\Current\Bin\MSBuild.exe" vsix/PaymentAssistant.sln /p:Configuration=Release /restore
```

`/restore` is needed on the first build only. The package lands at
`vsix/PaymentAssistant/bin/Release/PaymentAssistant.vsix` (~23 KB).

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

## What is verified

The build proves more than "it compiles". The generated
`bin/Release/PaymentAssistant.pkgdef` shows the shell registrations are correct, which is
where a hand-written VSIX usually goes wrong:

| Registration | Evidence in the `.pkgdef` |
|---|---|
| Package, async-loadable | `[$RootKey$\Packages\{c425ce3c-…}]` with `AllowsBackgroundLoad=1` |
| Command table | `[$RootKey$\Menus]` → `", Menus.ctmenu, 1"` |
| Tool window | `[$RootKey$\ToolWindows\{ec725a02-…}]`, `Style=Tabbed` |
| Options page | `[$RootKey$\ToolsOptionsPages\Payment Assistant\General]` |

The VSCT compiler also reports `errors = 0, warnings = 0`, so the menu placements
(`IDM_VS_CTXT_CODEWIN`, `IDM_VS_CTXT_ITEMNODE`) and the GUID/ID pairing between
`PaymentAssistantPackage.vsct` and the C# `CommandId` constants resolve.

## What is still unverified

Everything that only happens at runtime, because there is no IDE here to run it in:

- **The commands actually appearing** on the editor and Solution Explorer context menus,
  and `BeforeQueryStatus` hiding the file command for non-log types.
- **The WPF tool window rendering.** The XAML compiles to BAML, but `VsBrushes` theme
  binding and the `DialogWindow` base class are only exercised when the shell loads them.
- **`DTE` interop** — reading the editor selection and the Solution Explorer item.
- **The tool-window dock target** in `PaymentAssistantPackage.cs` is the Output window's
  well-known GUID. If the window docks oddly, drop the `Window = ...` argument; that is
  cosmetic only.
- **End-to-end against a live service** — the `HttpClient` call, the error envelope
  mapping, and the threading (`SwitchToMainThreadAsync` / `await TaskScheduler.Default`).

To exercise these, open the solution in the IDE and press **F5** (see [Debug](#debug)).

- **CI does not build this.** The pipeline runs on `ubuntu-latest`, which cannot build a
  VSIX. A Windows runner would now be worth adding, since the build is known to work.

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
