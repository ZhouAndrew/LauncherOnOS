package com.journalthree;

import android.app.Activity;
import android.app.AlertDialog;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.database.Cursor;
import android.database.SQLException;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.OpenableColumns;
import android.provider.MediaStore;
import android.text.Editable;
import android.text.InputType;
import android.text.TextWatcher;
import android.view.Gravity;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.view.inputmethod.InputMethodManager;
import android.widget.Button;
import android.widget.BaseAdapter;
import android.widget.EditText;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.ListView;
import android.widget.MediaController;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;
import android.widget.VideoView;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.text.DateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.List;
import java.util.UUID;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

public final class JournalActivity extends Activity {
    private static final int PAPER = Color.rgb(247, 246, 239);
    private static final int INK = Color.rgb(26, 43, 39);
    private static final int FOREST = Color.rgb(34, 75, 64);
    private static final int MUTED = Color.rgb(78, 96, 87);
    private static final int RULE = Color.rgb(218, 225, 213);
    private static final int PICK = 1;
    private static final int EXPORT = 2;
    private static final int CAPTURE = 3;

    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable autosave = this::save;
    private JournalStore store;
    private JournalStore.Note note;
    private String folder = JournalStore.DEFAULT;
    private String screen = "folders";
    private boolean dirty;
    private LinearLayout root;
    private FrameLayout editor;
    private ScrollView editorScroll;
    private NoteEditor noteEditor;
    private VideoView player;
    private FrameLayout playbackFrame;
    private MediaController videoControls;
    private int mediaStart;
    private String exportType;
    private String pendingCapture;
    private boolean searchMode;

    @Override public void onCreate(Bundle saved) {
        super.onCreate(saved);
        getWindow().setStatusBarColor(PAPER);
        getWindow().setNavigationBarColor(PAPER);
        getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        try {
            store = new JournalStore(getFilesDir());
        } catch (IOException | SQLException error) {
            new AlertDialog.Builder(this).setMessage("无法读取备忘录。请重新打开应用。")
                .setPositiveButton("关闭", (dialog, which) -> finish()).setCancelable(false).show();
            return;
        }
        if (saved == null) {
            showFolders();
            return;
        }
        folder = saved.getString("folder", JournalStore.DEFAULT);
        screen = saved.getString("screen", "folders");
        note = store.find(saved.getString("note"));
        mediaStart = saved.getInt("mediaStart");
        exportType = saved.getString("exportType");
        pendingCapture = saved.getString("pendingCapture");
        if ("editor".equals(screen)) {
            if (note == null) note = store.draft(folder);
            showEditor(false);
        } else if ("list".equals(screen)) {
            showList();
        } else {
            showFolders();
        }
    }

    @Override public void onSaveInstanceState(Bundle out) {
        save();
        super.onSaveInstanceState(out);
        out.putString("screen", screen);
        out.putString("folder", folder);
        out.putString("note", note == null ? null : note.id);
        out.putInt("mediaStart", mediaStart);
        out.putString("exportType", exportType);
        out.putString("pendingCapture", pendingCapture);
    }

    @Override public void onPause() {
        save();
        stopVideo();
        super.onPause();
    }

    @Override public void onDestroy() {
        handler.removeCallbacks(autosave);
        stopVideo();
        if (store != null) store.close();
        super.onDestroy();
    }

    @Override public void onBackPressed() {
        if ("editor".equals(screen)) {
            leaveEditor();
        } else if ("list".equals(screen)) {
            if (searchMode) {
                searchMode = false;
                showList();
            } else {
                showFolders();
            }
        } else {
            super.onBackPressed();
        }
    }

    private void leaveEditor() {
        if (!save()) return;
        hideKeyboard();
        note = null;
        showList();
    }

    private void finishEditing() {
        if (!save()) return;
        hideKeyboard();
        editor.requestFocus();
    }

    private void changed() {
        note.modified = System.currentTimeMillis();
        dirty = true;
        handler.removeCallbacks(autosave);
        handler.postDelayed(autosave, 240);
    }

    private boolean save() {
        handler.removeCallbacks(autosave);
        if (!dirty || note == null) return true;
        note.blocks.clear();
        note.blocks.addAll(noteEditor.blocks());
        if (!write(() -> store.saveNote(note))) return false;
        dirty = false;
        return true;
    }

    private boolean write(Runnable operation) {
        try {
            operation.run();
            return true;
        } catch (SQLException error) {
            android.util.Log.e("JournalThree", "Cannot save notes", error);
            toast("保存失败，请检查设备存储空间");
            return false;
        }
    }

    private int dp(float value) { return Math.round(value * getResources().getDisplayMetrics().density); }

    private LinearLayout vertical() {
        LinearLayout view = new LinearLayout(this);
        view.setOrientation(LinearLayout.VERTICAL);
        return view;
    }

    private LinearLayout horizontal() {
        LinearLayout view = new LinearLayout(this);
        view.setOrientation(LinearLayout.HORIZONTAL);
        view.setGravity(Gravity.CENTER_VERTICAL);
        return view;
    }

    private TextView text(String value, int size, int color) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextColor(color);
        view.setTextSize(size);
        return view;
    }

    private Button action(String label, Runnable run) {
        Button button = new Button(this, null, android.R.attr.borderlessButtonStyle);
        button.setText(label);
        button.setAllCaps(false);
        button.setTextColor(FOREST);
        button.setTextSize(14);
        button.setMinHeight(dp(48));
        button.setMinimumHeight(dp(48));
        button.setMinWidth(0);
        button.setMinimumWidth(0);
        button.setPadding(dp(10), 0, dp(10), 0);
        button.setOnClickListener(view -> run.run());
        return button;
    }

    private void page(String destination) {
        stopVideo();
        screen = destination;
        root = vertical();
        root.setBackgroundColor(PAPER);
        setContentView(root);
    }

    private void divider(LinearLayout layout) {
        View line = new View(this);
        line.setBackgroundColor(RULE);
        layout.addView(line, new LinearLayout.LayoutParams(-1, dp(1)));
    }

    private LinearLayout header(String title, String back, Runnable goBack) {
        LinearLayout bar = horizontal();
        bar.setPadding(dp(12), 0, dp(12), 0);
        if (back != null) bar.addView(action(back, goBack));
        TextView label = text(title, 17, INK);
        label.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
        bar.addView(label, new LinearLayout.LayoutParams(0, -2, 1));
        root.addView(bar, new LinearLayout.LayoutParams(-1, dp(57)));
        divider(root);
        return bar;
    }

    private LinearLayout scrollContent() {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        root.addView(scroll, new LinearLayout.LayoutParams(-1, 0, 1));
        LinearLayout content = vertical();
        content.setPadding(dp(20), dp(14), dp(20), dp(20));
        scroll.addView(content, new ScrollView.LayoutParams(-1, -2));
        return content;
    }

    private TextView label(String value) {
        TextView view = text(value, 14, MUTED);
        view.setPadding(0, dp(16), 0, dp(8));
        return view;
    }

    private void showFolders() {
        hideKeyboard();
        searchMode = false;
        page("folders");
        LinearLayout bar = header("日志三号", null, null);
        bar.addView(action("新建文件夹", this::newFolder));
        LinearLayout content = scrollContent();
        content.addView(label("此设备"));
        folderRow(content, "", "全部备忘录");
        for (JournalStore.Folder entry : store.folders()) folderRow(content, entry.id, entry.name);
        folderRow(content, JournalStore.TRASH, "最近删除");
        LinearLayout bottom = horizontal();
        bottom.setGravity(Gravity.END);
        bottom.setPadding(dp(12), 0, dp(12), 0);
        bottom.addView(action("新建备忘录", () -> {
            folder = JournalStore.DEFAULT;
            newNote();
        }));
        divider(root);
        root.addView(bottom);
    }

    private void folderRow(LinearLayout content, String id, String name) {
        LinearLayout row = horizontal();
        row.setMinimumHeight(dp(60));
        TextView nameView = text(name, 17, INK);
        row.addView(nameView, new LinearLayout.LayoutParams(0, -2, 1));
        int count = store.count(id);
        row.addView(text(String.valueOf(count), 14, MUTED));
        row.setContentDescription(name + "，" + count + " 条");
        row.setOnClickListener(view -> {
            folder = id;
            showList();
        });
        content.addView(row);
        divider(content);
    }

    private void newFolder() {
        EditText name = new EditText(this);
        name.setSingleLine(true);
        name.setHint("文件夹名称");
        AlertDialog dialog = new AlertDialog.Builder(this).setTitle("新建文件夹").setView(name)
            .setNegativeButton("取消", null).setPositiveButton("创建", null).create();
        dialog.setOnShowListener(unused -> dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener(button -> {
            String title = name.getText().toString().trim();
            if (title.isEmpty()) {
                name.setError("请输入文件夹名称");
                return;
            }
            JournalStore.Folder folder = new JournalStore.Folder(UUID.randomUUID().toString(), title);
            if (write(() -> store.createFolder(folder))) {
                dialog.dismiss();
                showFolders();
            }
        }));
        dialog.show();
    }

    private void showList() {
        page("list");
        LinearLayout bar = header(store.folderName(folder), "文件夹", this::showFolders);
        if (!JournalStore.TRASH.equals(folder)) {
            bar.addView(action(searchMode ? "取消搜索" : "搜索", () -> {
                searchMode = !searchMode;
                hideKeyboard();
                showList();
            }));
            bar.addView(action("新建", this::newNote));
        }
        EditText search = new EditText(this);
        if (searchMode) {
            search.setSingleLine(true);
            search.setHint("搜索备忘录");
            search.setContentDescription("搜索备忘录");
            root.addView(search, new LinearLayout.LayoutParams(-1, -2));
        }
        ListView content = new ListView(this);
        content.setPadding(dp(20), dp(14), dp(20), dp(20));
        content.setClipToPadding(false);
        content.setDivider(null);
        content.setSelector(android.R.color.transparent);
        NoteListAdapter adapter = new NoteListAdapter();
        content.setAdapter(adapter);
        root.addView(content, new LinearLayout.LayoutParams(-1, 0, 1));
        adapter.load("");
        if (searchMode) {
            search.addTextChangedListener(watcher(adapter::load));
            showKeyboard(search);
        }
    }

    private final class NoteListAdapter extends BaseAdapter {
        private final DateFormat dates = DateFormat.getDateInstance(DateFormat.MEDIUM);
        private List<JournalStore.Summary> matches = new ArrayList<>();
        private int pinned;
        private String emptyLabel;

        void load(String query) {
            matches = store.list(folder, query);
            pinned = 0;
            if (!JournalStore.TRASH.equals(folder)) {
                while (pinned < matches.size() && matches.get(pinned).pinned) pinned++;
            }
            emptyLabel = query.trim().isEmpty() ? "暂无备忘录" : "没有匹配的备忘录";
            notifyDataSetChanged();
        }

        @Override public int getCount() {
            if (matches.isEmpty()) return 1;
            if (pinned == 0) return matches.size();
            return matches.size() + (pinned == matches.size() ? 1 : 2);
        }

        @Override public JournalStore.Summary getItem(int position) {
            if (matches.isEmpty()) return null;
            if (pinned == 0) return matches.get(position);
            if (position == 0 || position == pinned + 1) return null;
            return matches.get(position - (position <= pinned ? 1 : 2));
        }

        @Override public long getItemId(int position) { return position; }
        @Override public int getViewTypeCount() { return 2; }
        @Override public int getItemViewType(int position) { return getItem(position) == null ? 0 : 1; }
        @Override public boolean areAllItemsEnabled() { return false; }
        @Override public boolean isEnabled(int position) { return getItem(position) != null; }

        @Override public View getView(int position, View recycled, ViewGroup parent) {
            JournalStore.Summary entry = getItem(position);
            if (entry == null) {
                String heading = matches.isEmpty() ? emptyLabel : (position == 0 ? "已置顶" : "备忘录");
                TextView view = recycled == null ? label(heading) : (TextView) recycled;
                view.setText(heading);
                return view;
            }
            return noteRow((LinearLayout) recycled, entry, dates.format(new Date(entry.modified)));
        }
    }

    private View noteRow(LinearLayout container, JournalStore.Summary entry, String date) {
        if (container == null) {
            container = vertical();
            LinearLayout row = vertical();
            row.setPadding(0, dp(14), 0, dp(14));
            TextView title = text("", 18, INK);
            title.setTypeface(Typeface.DEFAULT, Typeface.BOLD);
            title.setMaxLines(1);
            row.addView(title);
            TextView detail = text("", 13, MUTED);
            detail.setMaxLines(1);
            detail.setEllipsize(android.text.TextUtils.TruncateAt.END);
            row.addView(detail);
            container.addView(row);
            divider(container);
        }
        LinearLayout row = (LinearLayout) container.getChildAt(0);
        ((TextView) row.getChildAt(0)).setText(entry.title);
        String snippet = entry.preview.isEmpty() ? "" : "  " + entry.preview;
        ((TextView) row.getChildAt(1)).setText(date + snippet);
        row.setOnClickListener(view -> {
            JournalStore.Note selected = store.find(entry.id);
            if (selected == null) return;
            hideKeyboard();
            searchMode = false;
            note = selected;
            showEditor(false);
        });
        row.setOnLongClickListener(view -> {
            JournalStore.Note selected = store.find(entry.id);
            if (selected != null) noteActions(selected);
            return true;
        });
        row.setOnTouchListener(new View.OnTouchListener() {
            private float x;
            private float y;
            @Override public boolean onTouch(View view, MotionEvent event) {
                if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
                    x = event.getX();
                    y = event.getY();
                }
                if (event.getActionMasked() == MotionEvent.ACTION_UP &&
                    x - event.getX() > dp(80) && Math.abs(y - event.getY()) < dp(40)) {
                    view.cancelLongPress();
                    JournalStore.Note selected = store.find(entry.id);
                    if (selected != null) {
                        if (entry.deleted) noteActions(selected);
                        else confirmTrash(selected);
                    }
                    return true;
                }
                return false;
            }
        });
        return container;
    }

    private void newNote() {
        hideKeyboard();
        searchMode = false;
        note = store.draft(folder.isEmpty() ? JournalStore.DEFAULT : folder);
        showEditor(true);
    }

    private void noteActions(JournalStore.Note entry) {
        if (entry == note && (!save() || !note.hasContent())) return;
        String[] options = entry.deleted ? new String[]{"恢复", "永久删除"} :
            new String[]{entry.pinned ? "取消置顶" : "置顶", "移动", "删除"};
        new AlertDialog.Builder(this).setTitle(entry.title()).setItems(options, (dialog, choice) -> {
            if (entry.deleted) {
                if (choice == 0) {
                    entry.deleted = false;
                    if (write(() -> store.saveMetadata(entry))) refreshNoteScreen();
                    else entry.deleted = true;
                } else {
                    new AlertDialog.Builder(this).setMessage("永久删除这条备忘录？")
                        .setNegativeButton("取消", null).setPositiveButton("删除", (prompt, button) -> {
                            if (write(() -> store.deleteNote(entry.id))) {
                                for (JournalStore.Block block : entry.blocks) {
                                    if (block.media()) new File(store.media, block.file).delete();
                                }
                                if (note == entry) note = null;
                                showList();
                            }
                        }).show();
                }
            } else if (choice == 0) {
                entry.pinned = !entry.pinned;
                if (write(() -> store.saveMetadata(entry))) refreshNoteScreen();
                else entry.pinned = !entry.pinned;
            } else if (choice == 1) {
                moveNote(entry);
            } else {
                confirmTrash(entry);
            }
        }).show();
    }

    private void refreshNoteScreen() {
        if ("editor".equals(screen)) showEditor(false);
        else showList();
    }

    private void confirmTrash(JournalStore.Note entry) {
        new AlertDialog.Builder(this).setMessage("移到最近删除？")
            .setNegativeButton("取消", null).setPositiveButton("删除", (dialog, button) -> {
                entry.deleted = true;
                if (write(() -> store.saveMetadata(entry))) {
                    hideKeyboard();
                    note = null;
                    showList();
                } else {
                    entry.deleted = false;
                }
            }).show();
    }

    private void moveNote(JournalStore.Note entry) {
        List<JournalStore.Folder> folders = store.folders();
        String[] names = folders.stream().map(item -> item.name).toArray(String[]::new);
        new AlertDialog.Builder(this).setTitle("移动到文件夹").setItems(names, (dialog, i) -> {
            String previous = entry.folder;
            entry.folder = folders.get(i).id;
            if (write(() -> store.saveMetadata(entry))) refreshNoteScreen();
            else entry.folder = previous;
        }).show();
    }

    private void showEditor(boolean keyboard) {
        page("editor");
        LinearLayout bar = header("备忘录", "列表", this::leaveEditor);
        bar.addView(action("更多", this::editorMenu));
        if (!note.deleted) bar.addView(action("完成", this::finishEditing));
        editorScroll = new ScrollView(this);
        editorScroll.setFillViewport(true);
        root.addView(editorScroll, new LinearLayout.LayoutParams(-1, 0, 1));
        editor = new FrameLayout(this);
        editor.setFocusableInTouchMode(true);
        editorScroll.addView(editor, new ScrollView.LayoutParams(-1, -2));

        noteEditor = new NoteEditor(this, store.media);
        noteEditor.setContentDescription("备忘录正文");
        noteEditor.setTextColor(INK);
        noteEditor.setHintTextColor(MUTED);
        noteEditor.setBackgroundColor(Color.TRANSPARENT);
        noteEditor.setPadding(dp(20), dp(12), dp(20), dp(18));
        noteEditor.setGravity(Gravity.TOP);
        noteEditor.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE |
            InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        noteEditor.setTextSize(18);
        noteEditor.setHint("开始书写");
        noteEditor.load(note.blocks, note.deleted, this::playInline);
        noteEditor.addTextChangedListener(watcher(value -> {
            stopVideo();
            changed();
        }));
        editor.addView(noteEditor, new FrameLayout.LayoutParams(-1, -2));

        if (!note.deleted) {
            divider(root);
            LinearLayout toolbar = horizontal();
            toolbar.setGravity(Gravity.CENTER);
            toolbar.addView(action("格式", this::formatMenu));
            toolbar.addView(action("清单", () -> {
                noteEditor.insertChecklist();
                showKeyboard(noteEditor);
            }));
            toolbar.addView(action("附件", this::attachmentMenu));
            root.addView(toolbar, new LinearLayout.LayoutParams(-1, dp(52)));
        }
        if (keyboard) {
            noteEditor.setSelection(0);
            showKeyboard(noteEditor);
        } else {
            editor.requestFocus();
        }
    }

    private void playInline(NoteEditor.MediaSpan attachment) {
        File file = new File(store.media, attachment.block.file);
        if (!file.isFile()) {
            toast("找不到视频文件");
            return;
        }
        stopVideo();
        hideKeyboard();
        android.graphics.RectF bounds = attachment.bounds;
        VideoView video = new VideoView(this);
        player = video;
        FrameLayout.LayoutParams geometry = new FrameLayout.LayoutParams(
            (int) bounds.width(), (int) bounds.height());
        geometry.leftMargin = noteEditor.getTotalPaddingLeft() + (int) bounds.left;
        geometry.topMargin = noteEditor.getTotalPaddingTop() + (int) bounds.top;
        // VideoView measures itself to fit the decoded aspect ratio. Center it
        // within a fixed-size frame that occupies the original card.
        playbackFrame = new FrameLayout(this);
        playbackFrame.addView(video, new FrameLayout.LayoutParams(-1, -1, Gravity.CENTER));
        editor.addView(playbackFrame, geometry);
        videoControls = new MediaController(this);
        videoControls.setAnchorView(video);
        video.setMediaController(videoControls);
        video.setOnCompletionListener(completed -> {
            if (player == video) stopVideo();
        });
        video.setOnErrorListener((view, what, extra) -> {
            if (player == video) {
                stopVideo();
                toast("此视频无法播放");
            }
            return true;
        });
        video.setVideoPath(file.getAbsolutePath());
        video.start();
    }

    private void stopVideo() {
        VideoView video = player;
        if (video == null) return;
        player = null;
        videoControls.hide();
        videoControls = null;
        video.stopPlayback();
        editor.removeView(playbackFrame);
        playbackFrame = null;
    }

    private void editorMenu() {
        if (note.deleted) {
            noteActions(note);
            return;
        }
        new AlertDialog.Builder(this).setItems(new String[]{"导出 HTML", "导出 Markdown", "整理备忘录"},
            (dialog, choice) -> {
                if (choice == 2) noteActions(note);
                else beginExport(choice == 0 ? "html" : "md");
            }).show();
    }

    private void formatMenu() {
        new AlertDialog.Builder(this).setTitle("段落格式").setItems(new String[]{"正文", "标题"},
            (dialog, choice) -> {
                noteEditor.formatParagraph(choice == 1);
                changed();
                showKeyboard(noteEditor);
            }).show();
    }

    private void captureCaret() {
        int start = noteEditor.getSelectionStart();
        int end = noteEditor.getSelectionEnd();
        mediaStart = start < 0 || end < 0 ? noteEditor.length() : Math.min(start, end);
    }

    private void attachmentMenu() {
        captureCaret();
        if (!save()) return;
        new AlertDialog.Builder(this).setTitle("插入附件")
            .setItems(new String[]{"选择照片或视频", "拍照", "录制视频"}, (dialog, choice) -> {
                if (choice == 0) pickMedia();
                else captureMedia(choice == 2);
            }).show();
    }

    private void pickMedia() {
        Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
            .setType("*/*").putExtra(Intent.EXTRA_MIME_TYPES, new String[]{"image/*", "video/*"});
        try {
            startActivityForResult(picker, PICK);
        } catch (ActivityNotFoundException error) {
            toast("找不到系统文件选择器");
        }
    }

    private void captureMedia(boolean video) {
        pendingCapture = UUID.randomUUID().toString() + (video ? ".mp4" : ".jpg");
        Uri uri = CaptureProvider.uri(this, pendingCapture);
        Intent intent = new Intent(video ? MediaStore.ACTION_VIDEO_CAPTURE : MediaStore.ACTION_IMAGE_CAPTURE)
            .putExtra(MediaStore.EXTRA_OUTPUT, uri)
            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
        intent.setClipData(ClipData.newRawUri("Journal Three", uri));
        try {
            startActivityForResult(intent, CAPTURE);
        } catch (ActivityNotFoundException | SecurityException error) {
            pendingCapture = null;
            toast("找不到可用的相机");
        }
    }

    @Override public void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == CAPTURE) {
            finishCapture(result, data);
            return;
        }
        if (result != RESULT_OK || data == null || data.getData() == null || note == null) return;
        Uri uri = data.getData();
        if (request == PICK) importMedia(uri);
        if (request == EXPORT && exportType != null) writeExport(uri, exportType);
    }

    private void finishCapture(int result, Intent data) {
        String name = pendingCapture;
        pendingCapture = null;
        if (name == null) return;
        revokeUriPermission(CaptureProvider.uri(this, name),
            Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
        File file = new File(store.media, name);
        if (result != RESULT_OK || note == null) {
            file.delete();
        } else if (file.length() > 0) {
            boolean video = name.endsWith(".mp4");
            addMedia(video ? "video" : "image", video ? "录制视频.mp4" : "拍摄照片.jpg", name);
        } else {
            file.delete();
            Uri fallback = data == null ? null : data.getData();
            if (fallback == null) toast("相机未返回照片或视频");
            else importMedia(fallback);
        }
    }

    private void importMedia(Uri uri) {
        String type = getContentResolver().getType(uri);
        if (type == null || (!type.startsWith("image/") && !type.startsWith("video/"))) {
            toast("请选择照片或视频");
            return;
        }
        String name = mediaName(uri);
        String extension = android.webkit.MimeTypeMap.getSingleton().getExtensionFromMimeType(type);
        String fileName = UUID.randomUUID().toString() + (extension == null ? "" : "." + extension);
        File target = new File(store.media, fileName);
        JournalStore.Note destination = note;
        int start = mediaStart;
        AlertDialog progress = new AlertDialog.Builder(this).setMessage("正在导入附件")
            .setCancelable(false).show();
        new Thread(() -> {
            try (InputStream input = getContentResolver().openInputStream(uri);
                 OutputStream output = new FileOutputStream(target)) {
                if (input == null) throw new IOException("Cannot open attachment");
                if (copy(input, output) == 0) throw new IOException("Attachment is empty");
            } catch (IOException | SecurityException error) {
                target.delete();
                runOnUiThread(() -> {
                    if (!isDestroyed()) {
                        progress.dismiss();
                        toast("无法导入附件");
                    }
                });
                return;
            }
            runOnUiThread(() -> {
                if (isDestroyed() || note != destination) {
                    target.delete();
                    return;
                }
                progress.dismiss();
                mediaStart = start;
                addMedia(type.startsWith("video/") ? "video" : "image", name, fileName);
            });
        }, "journal-attachment").start();
    }

    private void addMedia(String kind, String label, String fileName) {
        JournalStore.Block item = new JournalStore.Block(kind, label);
        item.file = fileName;
        noteEditor.insertMedia(item, mediaStart);
        save();
        showKeyboard(noteEditor);
    }

    private String mediaName(Uri uri) {
        try (Cursor cursor = getContentResolver().query(uri, new String[]{OpenableColumns.DISPLAY_NAME},
                null, null, null)) {
            if (cursor != null && cursor.moveToFirst() && !cursor.isNull(0)) return cursor.getString(0);
        } catch (SecurityException error) {
            android.util.Log.w("JournalThree", "Cannot read attachment name", error);
        }
        return "附件";
    }

    private void beginExport(String type) {
        if (!save() || !note.hasContent()) return;
        exportType = type;
        String title = note.title().replaceAll("[\\\\/:*?\"<>|]", "_");
        if (title.length() > 60) title = title.substring(0, 60);
        Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
            .setType("application/zip").putExtra(Intent.EXTRA_TITLE, title + "." + type + ".zip");
        startActivityForResult(intent, EXPORT);
    }

    private void writeExport(Uri destination, String type) {
        boolean html = "html".equals(type);
        StringBuilder body = new StringBuilder();
        List<String> files = new ArrayList<>();
        if (html) body.append("<!doctype html><html lang=\"zh\"><meta charset=\"utf-8\"><title>")
            .append(escape(note.title())).append("</title><body>\n");
        for (JournalStore.Block block : note.blocks) {
            String value = block.text;
            if (block.media()) {
                files.add(block.file);
                String path = "media/" + block.file;
                if ("video".equals(block.kind)) {
                    body.append("<video controls src=\"").append(path).append("\"></video>\n\n");
                } else if (html) {
                    body.append("<img alt=\"").append(escape(value)).append("\" src=\"")
                        .append(path).append("\">\n");
                } else {
                    body.append("![").append(value.replace("[", "\\[").replace("]", "\\]"))
                        .append("](").append(path).append(")\n\n");
                }
            } else if (!value.isEmpty()) {
                String prefix = "check".equals(block.kind)
                    ? (block.checked ? "- [x] " : "- [ ] ") : ("heading".equals(block.kind) ? "## " : "");
                if (html) {
                    String tag = "heading".equals(block.kind) ? "h2" : "p";
                    String marker = "check".equals(block.kind) ? (block.checked ? "☑ " : "☐ ") : "";
                    body.append('<').append(tag).append('>').append(marker)
                        .append(escape(value).replace("\n", "<br>\n"))
                        .append("</").append(tag).append(">\n");
                } else {
                    body.append(prefix).append(value).append("\n\n");
                }
            }
        }
        if (html) body.append("</body></html>");
        byte[] document = body.toString().getBytes(StandardCharsets.UTF_8);
        new Thread(() -> {
            try (OutputStream stream = getContentResolver().openOutputStream(destination)) {
                if (stream == null) throw new IOException("Cannot open export destination");
                try (ZipOutputStream archive = new ZipOutputStream(stream)) {
                    archive.putNextEntry(new ZipEntry("note." + type));
                    archive.write(document);
                    archive.closeEntry();
                    for (String file : files) {
                        archive.putNextEntry(new ZipEntry("media/" + file));
                        try (InputStream source = new java.io.FileInputStream(new File(store.media, file))) {
                            copy(source, archive);
                        }
                        archive.closeEntry();
                    }
                }
                runOnUiThread(() -> toast("备忘录已导出"));
            } catch (IOException | SecurityException error) {
                runOnUiThread(() -> toast("导出失败"));
            }
        }, "journal-export").start();
    }

    private static long copy(InputStream source, OutputStream target) throws IOException {
        byte[] buffer = new byte[64 * 1024];
        long count = 0;
        int length;
        while ((length = source.read(buffer)) != -1) {
            target.write(buffer, 0, length);
            count += length;
        }
        return count;
    }

    private static String escape(String value) {
        return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            .replace("\"", "&quot;");
    }

    private TextWatcher watcher(java.util.function.Consumer<String> changedText) {
        return new TextWatcher() {
            @Override public void beforeTextChanged(CharSequence text, int start, int count, int after) {}
            @Override public void onTextChanged(CharSequence text, int start, int before, int count) {
                changedText.accept(text.toString());
            }
            @Override public void afterTextChanged(Editable text) {}
        };
    }

    private void showKeyboard(EditText field) {
        field.requestFocus();
        field.post(() -> {
            if (field.isFocused()) getSystemService(InputMethodManager.class)
                .showSoftInput(field, InputMethodManager.SHOW_IMPLICIT);
        });
    }

    private void hideKeyboard() {
        View focus = getCurrentFocus();
        if (focus != null) getSystemService(InputMethodManager.class)
            .hideSoftInputFromWindow(focus.getWindowToken(), 0);
    }

    private void toast(String message) { Toast.makeText(this, message, Toast.LENGTH_SHORT).show(); }
}
