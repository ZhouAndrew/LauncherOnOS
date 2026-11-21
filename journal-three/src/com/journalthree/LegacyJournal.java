package com.journalthree;

import android.util.AtomicFile;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.File;
import java.io.FileNotFoundException;
import java.io.IOException;
import java.nio.charset.StandardCharsets;

/** Reads the 0.1 archive once, during the SQLite schema creation transaction. */
final class LegacyJournal {
    static void importInto(File files, JournalStore store) throws IOException {
        AtomicFile archive = new AtomicFile(new File(files, "journal.json"));
        byte[] bytes;
        try {
            bytes = archive.readFully();
        } catch (FileNotFoundException absent) {
            if (archive.getBaseFile().exists()) throw absent;
            return;
        }
        try {
            JSONObject content = new JSONObject(new String(bytes, StandardCharsets.UTF_8));
            JSONArray folders = content.getJSONArray("folders");
            for (int index = 0; index < folders.length(); index++) {
                JSONObject folder = folders.getJSONObject(index);
                String id = folder.getString("id");
                if (!JournalStore.DEFAULT.equals(id)) {
                    store.createFolder(new JournalStore.Folder(id, folder.getString("name")));
                }
            }
            JSONArray notes = content.getJSONArray("notes");
            for (int index = 0; index < notes.length(); index++) {
                JSONObject saved = notes.getJSONObject(index);
                JournalStore.Note note = new JournalStore.Note(saved.getString("id"), saved.getString("folder"));
                note.modified = saved.getLong("modified");
                note.pinned = saved.optBoolean("pinned");
                note.deleted = saved.optBoolean("deleted");
                JSONArray blocks = saved.getJSONArray("blocks");
                for (int position = 0; position < blocks.length(); position++) {
                    JSONObject item = blocks.getJSONObject(position);
                    JournalStore.Block block = new JournalStore.Block(item.getString("kind"), item.getString("text"));
                    block.file = item.optString("file");
                    block.checked = item.optBoolean("checked");
                    note.blocks.add(block);
                }
                store.saveNote(note);
            }
        } catch (JSONException invalidArchive) {
            throw new IOException("Cannot migrate the 0.1 notes archive", invalidArchive);
        }
    }

    private LegacyJournal() {}
}
