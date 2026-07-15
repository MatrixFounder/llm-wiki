// Vendored MINIMAL ambient declaration for the "obsidian" plugin API — TASK 068 / R-068-1.
//
// This is NOT the full upstream `obsidian.d.ts`; it declares ONLY the symbols `main.ts`
// touches (Plugin, App, Editor, EditorPosition, MarkdownView, TFile, DataAdapter, Notice,
// Command), each with a REAL (non-`any`) signature. An all-`any` stub would make
// `tsc --noEmit` pass vacuously (explicit `any` escapes `strict`/`noImplicitAny`), which
// would silently defeat the whole point of the R-068-1 type-check gate — see
// `docs/tasks/task-068-01-plugin-skeleton.md` TC-04 (the negative-control test that proves
// this file is not all-`any`).
//
// Kept in lockstep, by hand, with the real npm "obsidian" module's shape for the members
// actually used here. If a future task needs another symbol/member, add it here (and only
// here) rather than reaching for `any`.

declare module "obsidian" {
  export interface EditorPosition {
    line: number;
    ch: number;
  }

  export interface Editor {
    getValue(): string;
    getRange(from: EditorPosition, to: EditorPosition): string;
    replaceRange(replacement: string, from: EditorPosition, to: EditorPosition): void;
    getCursor(side?: string): EditorPosition;
    somethingSelected(): boolean;
    posToOffset(pos: EditorPosition): number;
  }

  export interface FileStats {
    ctime: number;
    mtime: number;
    size: number;
  }

  export class TFile {
    path: string;
    name: string;
    extension: string;
    stat: FileStats;
  }

  // The shape `workspace.activeEditor` carries — a focused Markdown editor's file/editor,
  // whether the active leaf is a full `MarkdownView` or a lighter editor-hosting view.
  // `getMode` is optional here (not every `MarkdownFileInfo` implementer exposes it) — the
  // plugin always calls it via `ed.getMode?.()`, never a bare call.
  export interface MarkdownFileInfo {
    file: TFile | null;
    editor?: Editor;
    getMode?(): string;
    save(): Promise<void>;
  }

  export class MarkdownView implements MarkdownFileInfo {
    file: TFile | null;
    editor: Editor;
    getMode(): string;
    save(): Promise<void>;
  }

  export interface DataAdapter {
    read(normalizedPath: string): Promise<string>;
    write(normalizedPath: string, data: string): Promise<void>;
    exists(normalizedPath: string): Promise<boolean>;
  }

  export class Vault {
    adapter: DataAdapter;
    getName(): string;
  }

  export class Workspace {
    activeEditor: MarkdownFileInfo | null;
  }

  export class App {
    vault: Vault;
    workspace: Workspace;
  }

  export interface Command {
    id: string;
    name: string;
    callback?: () => unknown;
  }

  export abstract class Plugin {
    app: App;
    constructor(app: App, manifest: unknown);
    addCommand(command: Command): Command;
    onload(): void | Promise<void>;
    onunload(): void | Promise<void>;
  }

  export class Notice {
    constructor(message: string, timeout?: number);
  }
}
