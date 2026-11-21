package com.journalthree;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Context;
import android.content.Intent;
import android.view.View;
import android.view.ViewGroup;
import android.widget.TextView;
import android.database.SQLException;
import android.database.sqlite.SQLiteDatabase;
import android.os.Bundle;
import android.os.SystemClock;
import android.view.MotionEvent;
import android.widget.VideoView;

import java.io.File;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.Arrays;
import java.util.List;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.BooleanSupplier;

public final class StoreAcceptance extends Instrumentation {
    @Override public void onCreate(Bundle arguments) {
        super.onCreate(arguments);
        start();
    }

    @Override public void onStart() {
        Bundle result = new Bundle();
        try {
            verify(getTargetContext());
            verifyEditor(getTargetContext());
            verifyPlayback(getTargetContext());
            result.putString("stream", "\nPASS: SQLite create, legacy migration, ordered blocks, "
                + "search, edits, folders, trash, reopen and rollback\n"
                + "PASS: continuous editor, cross-media selection and replacement, SQLite readback\n"
                + "PASS: tapped in-body H.264 MP4, playback centered, advanced and returned to the note\n");
            finish(Activity.RESULT_OK, result);
        } catch (Throwable error) {
            result.putString("stream", android.util.Log.getStackTraceString(error));
            finish(Activity.RESULT_CANCELED, result);
        }
    }

    private void verifyEditor(Context context) throws Exception {
        Intent launch = new Intent(context, JournalActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        Activity activity = startActivitySync(launch);
        String title = "Editor acceptance " + UUID.randomUUID();
        runOnMainSync(() -> {
            View root = activity.findViewById(android.R.id.content);
            button(root, "新建备忘录").performClick();
            NoteEditor field = editor(root);
            require(field != null, "one editor after tapping new note");
            field.getText().append(title + "\nBeforeAfter");
            JournalStore.Block photo = new JournalStore.Block("image", "acceptance photo");
            photo.file = "acceptance.png";
            field.insertMedia(photo, field.length() - "After".length());
            JournalStore.Block video = new JournalStore.Block("video", "acceptance video");
            video.file = "acceptance.mp4";
            field.insertMedia(video, field.getSelectionEnd());
            int first = title.length() + 1;
            field.setSelection(first, field.length());
            require(field.getSelectionStart() == first && field.getSelectionEnd() == field.length(),
                "one native range across both attachments");
            List<JournalStore.Block> blocks = field.blocks();
            require(blocks.size() == 4 && blocks.get(1).file.equals(photo.file)
                && blocks.get(2).file.equals(video.file) && blocks.get(3).text.equals("After"),
                "insert at caret in visible editor");
            button(root, "完成").performClick();
        });
        waitForIdleSync();
        String id;
        try (JournalStore store = new JournalStore(context.getFilesDir())) {
            id = store.list("", title).get(0).id;
            require(store.find(id).blocks.size() == 4, "Done saves ordered attachments to SQLite");
        }
        runOnMainSync(() -> {
            View root = activity.findViewById(android.R.id.content);
            button(root, "列表").performClick();
        });
        waitForIdleSync();
        runOnMainSync(() -> {
            View root = activity.findViewById(android.R.id.content);
            View titleView = button(root, title);
            ((View) titleView.getParent()).performClick();
            NoteEditor field = editor(root);
            require(field != null && field.blocks().size() == 4, "open mixed note from actual list");
            field.setSelection(title.length() + 1, field.length());
            field.getText().replace(field.getSelectionStart(), field.getSelectionEnd(), "Replacement");
            require(field.blocks().size() == 1 && field.blocks().get(0).text.endsWith("Replacement"),
                "replacing range removes both attachment tokens");
            button(root, "完成").performClick();
            activity.finish();
        });
        waitForIdleSync();
        try (JournalStore store = new JournalStore(context.getFilesDir())) {
            JournalStore.Note saved = store.find(id);
            require(saved.blocks.size() == 1 && saved.blocks.get(0).text.equals(title + "\nReplacement"),
                "replacement survives close and SQLite reopen");
            store.deleteNote(id);
        }
    }

    private void verifyPlayback(Context context) throws Exception {
        String fileName = "acceptance-" + UUID.randomUUID() + ".mp4";
        File file = new File(context.getFilesDir(), "media/" + fileName);
        try (InputStream input = getContext().getAssets().open("playback.mp4")) {
            Files.copy(input, file.toPath());
        }
        Activity activity = startActivitySync(new Intent(context, JournalActivity.class)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        View root = activity.findViewById(android.R.id.content);
        String title = "Playback acceptance " + UUID.randomUUID();
        try {
            runOnMainSync(() -> {
                button(root, "新建备忘录").performClick();
                NoteEditor field = editor(root);
                field.getText().append(title + "\n");
                JournalStore.Block video = new JournalStore.Block("video", "acceptance clip");
                video.file = fileName;
                field.insertMedia(video, field.length());
                button(root, "完成").performClick();
            });
            awaitUi(() -> {
                NoteEditor field = editor(root);
                NoteEditor.MediaSpan[] spans = field.getText().getSpans(0, field.length(), NoteEditor.MediaSpan.class);
                return spans.length == 1 && !spans[0].bounds.isEmpty();
            }, "video placeholder rendered in the note");
            runOnMainSync(() -> {
                NoteEditor field = editor(root);
                NoteEditor.MediaSpan span = field.getText().getSpans(0, field.length(), NoteEditor.MediaSpan.class)[0];
                int[] screen = new int[2];
                field.getLocationOnScreen(screen);
                float x = screen[0] + field.getTotalPaddingLeft() + span.bounds.centerX();
                float y = screen[1] + field.getTotalPaddingTop() + span.bounds.centerY();
                long now = SystemClock.uptimeMillis();
                MotionEvent down = MotionEvent.obtain(now, now, MotionEvent.ACTION_DOWN, x, y, 0);
                MotionEvent up = MotionEvent.obtain(now, now + 40, MotionEvent.ACTION_UP, x, y, 0);
                activity.dispatchTouchEvent(down);
                activity.dispatchTouchEvent(up);
                down.recycle();
                up.recycle();
            });
            awaitUi(() -> {
                VideoView playing = videoView(root);
                if (playing == null || !playing.isPlaying() || playing.getCurrentPosition() < 200) return false;
                NoteEditor field = editor(root);
                NoteEditor.MediaSpan card = field.getText()
                    .getSpans(0, field.length(), NoteEditor.MediaSpan.class)[0];
                int[] editorLocation = new int[2];
                int[] videoLocation = new int[2];
                field.getLocationOnScreen(editorLocation);
                playing.getLocationOnScreen(videoLocation);
                double cardCenter = editorLocation[0] + field.getTotalPaddingLeft() + card.bounds.centerX();
                double videoCenter = videoLocation[0] + playing.getWidth() / 2.0;
                return playing.getWidth() > 0 && playing.getWidth() < card.bounds.width()
                    && Math.abs(videoCenter - cardCenter) <= 1;
            }, "inline player advances and is horizontally centered in the card");
            awaitUi(() -> videoView(root) == null && editor(root) != null,
                "completed playback returns to the video placeholder");
        } finally {
            runOnMainSync(activity::finish);
            waitForIdleSync();
            try (JournalStore store = new JournalStore(context.getFilesDir())) {
                for (JournalStore.Summary match : store.list("", title)) store.deleteNote(match.id);
            }
            Files.deleteIfExists(file.toPath());
        }
    }

    private void awaitUi(BooleanSupplier condition, String description) {
        AtomicBoolean passed = new AtomicBoolean();
        long deadline = SystemClock.uptimeMillis() + 30_000;
        do {
            runOnMainSync(() -> passed.set(condition.getAsBoolean()));
            if (passed.get()) return;
            SystemClock.sleep(80);
        } while (SystemClock.uptimeMillis() < deadline);
        throw new AssertionError(description);
    }

    private static VideoView videoView(View view) {
        if (view instanceof VideoView) return (VideoView) view;
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int index = 0; index < group.getChildCount(); index++) {
                VideoView found = videoView(group.getChildAt(index));
                if (found != null) return found;
            }
        }
        return null;
    }

    private static View button(View root, String label) {
        View found = labelledView(root, label);
        if (found == null) throw new AssertionError("Missing view: " + label);
        return found;
    }

    private static View labelledView(View view, String label) {
        if (view instanceof TextView && label.contentEquals(((TextView) view).getText())) return view;
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int index = 0; index < group.getChildCount(); index++) {
                View found = labelledView(group.getChildAt(index), label);
                if (found != null) return found;
            }
        }
        return null;
    }

    private static NoteEditor editor(View view) {
        if (view instanceof NoteEditor) return (NoteEditor) view;
        if (view instanceof ViewGroup) {
            ViewGroup group = (ViewGroup) view;
            for (int index = 0; index < group.getChildCount(); index++) {
                NoteEditor found = editor(group.getChildAt(index));
                if (found != null) return found;
            }
        }
        return null;
    }

    private static void verify(Context context) throws Exception {
        File root = new File(context.getCacheDir(), "sql-test-" + UUID.randomUUID());
        require(root.mkdir(), "make scratch directory");
        File legacy = new File(root, "journal.json");
        File media = new File(root, "media");
        require(media.mkdir(), "make media directory");
        byte[] originalPhoto = {1, 2, 3, 4};
        Files.write(new File(media, "photo.png").toPath(), originalPhoto);
        byte[] fixture = ("{\"folders\":[{\"id\":\"notes\",\"name\":\"备忘录\"},{\"id\":\"work\",\"name\":\"工作\"}],"
            + "\"notes\":[{\"id\":\"original\",\"folder\":\"work\",\"modified\":100,\"pinned\":true,\"deleted\":false,"
            + "\"blocks\":[{\"kind\":\"text\",\"text\":\"旅行\\nBefore\"},{\"kind\":\"image\",\"text\":\"Photo\",\"file\":\"photo.png\"},"
            + "{\"kind\":\"check\",\"text\":\"After\",\"checked\":true}]}]}").getBytes(StandardCharsets.UTF_8);
        Files.write(legacy.toPath(), fixture);
        String newId;
        try (JournalStore store = new JournalStore(root)) {
            require(store.folders().size() == 2, "folder migration");
            JournalStore.Note note = store.find("original");
            require(note.pinned && note.modified == 100 && note.folder.equals("work"), "note metadata migration");
            require(note.blocks.size() == 3 && note.blocks.get(1).file.equals("photo.png")
                && note.blocks.get(2).checked, "ordered media and checklist migration");
            require(Arrays.equals(Files.readAllBytes(new File(store.media, "photo.png").toPath()), originalPhoto),
                "original media bytes");
            require(store.list("work", "旅行").get(0).title.equals("旅行"), "Chinese search and title");
            require(store.list("work", "AFTER").size() == 1 && store.list("work", "%").isEmpty(),
                "case folding and literal search");
            store.createFolder(new JournalStore.Folder("moved", "移动"));
            JournalStore.Note created = store.draft("moved");
            newId = created.id;
            created.blocks.get(0).text = "新备忘录";
            store.saveNote(created);
            store.saveNote(created);
            require(store.count("moved") == 1, "single record across repeat writes");
            note.blocks.get(0).text = "旅行修订";
            note.blocks.remove(1);
            store.saveNote(note);
            note.folder = "moved";
            note.deleted = true;
            store.saveMetadata(note);
            require(store.count("work") == 0 && store.count(JournalStore.TRASH) == 1, "move and trash");
        }
        require(Arrays.equals(Files.readAllBytes(legacy.toPath()), fixture), "legacy archive remains untouched");
        try (JournalStore store = new JournalStore(root)) {
            JournalStore.Note note = store.find("original");
            require(note.deleted && note.folder.equals("moved") && note.blocks.size() == 2
                && note.blocks.get(0).text.equals("旅行修订") && note.blocks.get(1).checked, "readback after reopen");
            note.deleted = false;
            store.saveMetadata(note);
            List<JournalStore.Summary> active = store.list("", "");
            require(active.size() == 2 && active.get(0).id.equals("original"), "restore and pin ordering");
            store.deleteNote("original");
            require(store.find("original") == null, "delete note");
            JournalStore.Note created = store.find(newId);
            created.blocks.get(0).text = "";
            store.saveNote(created);
            require(store.count("") == 0, "empty note removal");
        }
        try (SQLiteDatabase database = SQLiteDatabase.openDatabase(
                new File(root, "database/journal.sqlite").getPath(), null, SQLiteDatabase.OPEN_READONLY)) {
            require(android.database.DatabaseUtils.longForQuery(database, "SELECT count(*) FROM note_blocks", null) == 0,
                "foreign-key cascade");
        }

        File failed = new File(context.getCacheDir(), "sql-failed-" + UUID.randomUUID());
        require(failed.mkdir(), "make failed-migration directory");
        File failedArchive = new File(failed, "journal.json");
        String invalid = new String(fixture, StandardCharsets.UTF_8)
            .replace("\"folder\":\"work\"", "\"folder\":\"missing\"");
        Files.write(failedArchive.toPath(), invalid.getBytes(StandardCharsets.UTF_8));
        try (JournalStore ignored = new JournalStore(failed)) {
            throw new AssertionError("foreign-key violation must roll back migration");
        } catch (SQLException expected) {
            require(Files.readAllBytes(failedArchive.toPath()).length > 0, "failed migration retains original");
        }
        Files.write(failedArchive.toPath(), fixture);
        try (JournalStore recovered = new JournalStore(failed)) {
            require(recovered.find("original") != null, "migration can retry after rollback");
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) throw new AssertionError(message);
    }
}
