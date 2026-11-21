package com.journalthree;

import android.content.ContentValues;
import android.database.Cursor;
import android.database.DatabaseUtils;
import android.database.SQLException;
import android.database.sqlite.SQLiteDatabase;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.UUID;

final class JournalStore implements AutoCloseable {
    static final String DEFAULT = "notes";
    static final String TRASH = "trash";
    private static final int VERSION = 1;
    private static final String[] SUMMARY_COLUMNS = {"id", "title", "preview", "modified", "pinned", "deleted"};

    static final class Folder {
        final String id;
        final String name;
        Folder(String id, String name) { this.id = id; this.name = name; }
    }

    static final class Block {
        String kind;
        String text;
        String file = "";
        boolean checked;

        Block(String kind, String text) { this.kind = kind; this.text = text; }

        boolean media() { return kind.equals("image") || kind.equals("video"); }
    }

    static final class Note {
        final String id;
        String folder;
        long modified = System.currentTimeMillis();
        boolean pinned;
        boolean deleted;
        final List<Block> blocks = new ArrayList<>();

        Note(String id, String folder) { this.id = id; this.folder = folder; }

        String title() {
            for (Block block : blocks) {
                if (!block.media() && !block.text.trim().isEmpty()) {
                    return block.text.trim().split("\\R", 2)[0];
                }
            }
            return "无标题";
        }

        String body() {
            StringBuilder text = new StringBuilder();
            for (Block block : blocks) {
                if (text.length() > 0) text.append('\n');
                text.append(block.text);
            }
            return text.toString();
        }

        boolean hasContent() {
            for (Block block : blocks) if (block.media() || block.kind.equals("check") || !block.text.trim().isEmpty()) return true;
            return false;
        }
    }

    static final class Summary {
        final String id;
        final String title;
        final String preview;
        final long modified;
        final boolean pinned;
        final boolean deleted;

        Summary(Cursor cursor) {
            id = cursor.getString(0);
            title = cursor.getString(1);
            preview = cursor.getString(2);
            modified = cursor.getLong(3);
            pinned = cursor.getInt(4) != 0;
            deleted = cursor.getInt(5) != 0;
        }
    }

    final File media;
    private final SQLiteDatabase db;

    JournalStore(File files) throws IOException {
        media = new File(files, "media");
        if (!media.isDirectory() && !media.mkdirs()) throw new IOException("Cannot create media directory");
        File databaseDir = new File(files, "database");
        if (!databaseDir.isDirectory() && !databaseDir.mkdirs()) {
            throw new IOException("Cannot create database directory");
        }
        db = SQLiteDatabase.openOrCreateDatabase(new File(databaseDir, "journal.sqlite"), null);
        try {
            db.setForeignKeyConstraintsEnabled(true);
            db.enableWriteAheadLogging();
            initialize(files);
        } catch (IOException | RuntimeException error) {
            close();
            throw error;
        }
    }

    private void initialize(File files) throws IOException {
        if (db.getVersion() == VERSION) return;
        db.beginTransaction();
        try {
            int version = db.getVersion();
            if (version == 0) {
                db.execSQL("CREATE TABLE folders (id TEXT PRIMARY KEY NOT NULL, name TEXT NOT NULL)");
                db.execSQL("CREATE TABLE notes (id TEXT PRIMARY KEY NOT NULL, folder_id TEXT NOT NULL "
                    + "REFERENCES folders(id), modified INTEGER NOT NULL, pinned INTEGER NOT NULL, "
                    + "deleted INTEGER NOT NULL, title TEXT NOT NULL, preview TEXT NOT NULL, search_text TEXT NOT NULL)");
                db.execSQL("CREATE TABLE note_blocks (note_id TEXT NOT NULL REFERENCES notes(id) ON DELETE CASCADE, "
                    + "position INTEGER NOT NULL, kind TEXT NOT NULL, body TEXT NOT NULL, "
                    + "media_file TEXT NOT NULL, checked INTEGER NOT NULL, PRIMARY KEY(note_id, position))");
                db.execSQL("CREATE INDEX notes_active_order ON notes(deleted, pinned DESC, modified DESC, id)");
                db.execSQL("CREATE INDEX notes_folder_order ON notes(folder_id, deleted, pinned DESC, modified DESC, id)");
                db.execSQL("CREATE INDEX notes_trash_order ON notes(deleted, modified DESC, id)");
                createFolder(new Folder(DEFAULT, "备忘录"));
                LegacyJournal.importInto(files, this);
                db.setVersion(VERSION);
            } else if (version != VERSION) {
                throw new IOException("Unsupported notes database version: " + version);
            }
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    List<Folder> folders() {
        List<Folder> result = new ArrayList<>();
        try (Cursor rows = db.rawQuery("SELECT id, name FROM folders ORDER BY rowid", null)) {
            while (rows.moveToNext()) result.add(new Folder(rows.getString(0), rows.getString(1)));
        }
        return result;
    }

    void createFolder(Folder folder) {
        ContentValues values = new ContentValues();
        values.put("id", folder.id);
        values.put("name", folder.name);
        db.insertOrThrow("folders", null, values);
    }

    String folderName(String id) {
        if (TRASH.equals(id)) return "最近删除";
        try (Cursor rows = db.rawQuery("SELECT name FROM folders WHERE id = ?", new String[]{id})) {
            return rows.moveToFirst() ? rows.getString(0) : "全部备忘录";
        }
    }

    int count(String folder) {
        String sql = "SELECT count(*) FROM notes WHERE " + selection(folder);
        return (int) DatabaseUtils.longForQuery(db, sql, selectionArgs(folder));
    }

    List<Summary> list(String folder, String query) {
        String needle = query.trim().toLowerCase(Locale.ROOT);
        String where = selection(folder);
        String[] args = selectionArgs(folder);
        if (!needle.isEmpty()) {
            where += " AND instr(search_text, ?) > 0";
            args = args.length == 0 ? new String[]{needle} : new String[]{args[0], needle};
        }
        String order = TRASH.equals(folder) ? "modified DESC, id" : "pinned DESC, modified DESC, id";
        List<Summary> result = new ArrayList<>();
        try (Cursor rows = db.query("notes", SUMMARY_COLUMNS, where, args, null, null, order)) {
            while (rows.moveToNext()) result.add(new Summary(rows));
        }
        return result;
    }

    private static String selection(String folder) {
        if (TRASH.equals(folder)) return "deleted = 1";
        return folder.isEmpty() ? "deleted = 0" : "deleted = 0 AND folder_id = ?";
    }

    private static String[] selectionArgs(String folder) {
        return folder.isEmpty() || TRASH.equals(folder) ? new String[0] : new String[]{folder};
    }

    Note find(String id) {
        if (id == null) return null;
        String[] args = {id};
        Note note;
        try (Cursor rows = db.rawQuery("SELECT folder_id, modified, pinned, deleted FROM notes WHERE id = ?", args)) {
            if (!rows.moveToFirst()) return null;
            note = new Note(id, rows.getString(0));
            note.modified = rows.getLong(1);
            note.pinned = rows.getInt(2) != 0;
            note.deleted = rows.getInt(3) != 0;
        }
        try (Cursor rows = db.rawQuery("SELECT kind, body, media_file, checked FROM note_blocks "
                + "WHERE note_id = ? ORDER BY position", args)) {
            while (rows.moveToNext()) {
                Block block = new Block(rows.getString(0), rows.getString(1));
                block.file = rows.getString(2);
                block.checked = rows.getInt(3) != 0;
                note.blocks.add(block);
            }
        }
        return note;
    }

    Note draft(String folder) {
        Note note = new Note(UUID.randomUUID().toString(), folder);
        note.blocks.add(new Block("text", ""));
        return note;
    }

    void saveNote(Note note) {
        if (!note.hasContent()) {
            deleteNote(note.id);
            return;
        }
        String[] key = {note.id};
        db.beginTransaction();
        try {
            ContentValues values = metadata(note);
            values.put("title", note.title());
            String body = note.body();
            String[] lines = body.trim().split("\\R", 2);
            String preview = lines.length > 1 ? lines[1].replace('\n', ' ') : "";
            values.put("preview", preview.substring(0, Math.min(preview.length(), 280)));
            values.put("search_text", body.toLowerCase(Locale.ROOT));
            if (db.update("notes", values, "id = ?", key) == 0) {
                values.put("id", note.id);
                db.insertOrThrow("notes", null, values);
            }
            updateBlocks(note);
            db.setTransactionSuccessful();
        } finally {
            db.endTransaction();
        }
    }

    private void updateBlocks(Note note) {
        // Compare the ordered rows so a keystroke writes only the affected block.
        List<Integer> changed = new ArrayList<>();
        int index = 0;
        try (Cursor rows = db.rawQuery("SELECT position, kind, body, media_file, checked FROM note_blocks "
                + "WHERE note_id = ? ORDER BY position", new String[]{note.id})) {
            while (index < note.blocks.size() && rows.moveToNext()) {
                Block block = note.blocks.get(index);
                if (rows.getInt(0) != index) throw new SQLException("Non-contiguous note blocks");
                if (!block.kind.equals(rows.getString(1)) || !block.text.equals(rows.getString(2))
                    || !block.file.equals(rows.getString(3)) || block.checked != (rows.getInt(4) != 0)) {
                    changed.add(index);
                }
                index++;
            }
        }
        for (int position : changed) writeBlock(note, position, false);
        for (int position = index; position < note.blocks.size(); position++) writeBlock(note, position, true);
        db.delete("note_blocks", "note_id = ? AND position >= ?",
            new String[]{note.id, String.valueOf(note.blocks.size())});
    }

    private void writeBlock(Note note, int position, boolean insert) {
        Block block = note.blocks.get(position);
        ContentValues values = new ContentValues();
        values.put("kind", block.kind);
        values.put("body", block.text);
        values.put("media_file", block.file);
        values.put("checked", block.checked ? 1 : 0);
        if (insert) {
            values.put("note_id", note.id);
            values.put("position", position);
            db.insertOrThrow("note_blocks", null, values);
        } else {
            db.update("note_blocks", values, "note_id = ? AND position = ?",
                new String[]{note.id, String.valueOf(position)});
        }
    }

    void saveMetadata(Note note) {
        db.update("notes", metadata(note), "id = ?", new String[]{note.id});
    }

    private static ContentValues metadata(Note note) {
        ContentValues values = new ContentValues();
        values.put("folder_id", note.folder);
        values.put("modified", note.modified);
        values.put("pinned", note.pinned ? 1 : 0);
        values.put("deleted", note.deleted ? 1 : 0);
        return values;
    }

    void deleteNote(String id) {
        db.delete("notes", "id = ?", new String[]{id});
    }

    @Override public void close() { db.close(); }
}
