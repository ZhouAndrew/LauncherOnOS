package com.journalthree;

import android.content.ClipData;
import android.content.ClipboardManager;
import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Canvas;
import android.graphics.Paint;
import android.graphics.RectF;
import android.text.Editable;
import android.text.SpannableStringBuilder;
import android.text.Spanned;
import android.text.style.ReplacementSpan;
import android.util.LruCache;
import android.view.MotionEvent;
import android.widget.EditText;

import java.io.File;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** One Android text buffer and selection for the entire note. */
final class NoteEditor extends EditText {
    private static final char OBJECT = '\uFFFC';
    private static final int EXCLUSIVE = Spanned.SPAN_EXCLUSIVE_EXCLUSIVE;
    private static final int PANEL = 0xffe5ede2;
    private static final int FOREST = 0xff224b40;
    private final File media;
    private final ExecutorService previews = Executors.newFixedThreadPool(2);
    private final LruCache<String, Bitmap> bitmaps = new LruCache<String, Bitmap>(12 * 1024 * 1024) {
        @Override protected int sizeOf(String path, Bitmap bitmap) { return bitmap.getAllocationByteCount(); }
    };
    private final java.util.Set<String> loading = new java.util.HashSet<>();
    private final java.util.Set<String> unavailable = new java.util.HashSet<>();
    private final float slop;
    private float downX;
    private float downY;
    private long downTime;
    private boolean readOnly;
    private int availableWidth;
    private VideoAction videoAction;

    interface VideoAction { void open(MediaSpan span); }

    NoteEditor(Context context, File media) {
        super(context);
        this.media = media;
        slop = android.view.ViewConfiguration.get(context).getScaledTouchSlop();
    }

    void load(List<JournalStore.Block> blocks, boolean readOnly, VideoAction videoAction) {
        this.readOnly = readOnly;
        this.videoAction = videoAction;
        SpannableStringBuilder body = new SpannableStringBuilder();
        JournalStore.Block previous = null;
        for (JournalStore.Block block : blocks) {
            if (previous != null && !previous.media() && !block.media() && body.length() > 0
                && body.charAt(body.length() - 1) != '\n' && !block.text.startsWith("\n")) {
                body.append('\n');
            }
            if (block.media()) {
                appendObject(body, new MediaSpan(block));
            } else {
                if (block.kind.equals("check")) appendObject(body, new CheckSpan(block.checked));
                int start = body.length();
                body.append(block.text);
                if (block.kind.equals("heading") && body.length() > start) {
                    body.setSpan(new Heading(), start, body.length(), EXCLUSIVE);
                }
            }
            previous = block;
        }
        setText(body, BufferType.EDITABLE);
        if (readOnly) {
            setKeyListener(null);
            setTextIsSelectable(true);
        }
    }

    List<JournalStore.Block> blocks() {
        Editable text = getText();
        List<JournalStore.Block> result = new ArrayList<>();
        String kind = "text";
        boolean checked = false;
        StringBuilder segment = new StringBuilder();
        int offset = 0;
        while (offset < text.length()) {
            int transition = text.nextSpanTransition(offset, text.length(), android.text.style.CharacterStyle.class);
            MediaSpan picture = objectAt(offset, MediaSpan.class);
            CheckSpan check = objectAt(offset, CheckSpan.class);
            boolean heading = text.getSpans(offset, offset + 1, Heading.class).length > 0;
            if (picture != null || check != null || kind.equals("heading") != heading && !kind.equals("check")) {
                appendBlock(result, kind, segment, checked);
                kind = heading ? "heading" : "text";
            }
            if (picture != null) {
                result.add(picture.block);
            } else if (check != null) {
                kind = "check";
                checked = check.checked;
            } else {
                for (int index = offset; index < transition; index++) {
                    char value = text.charAt(index);
                    if (value == OBJECT) continue;
                    if (kind.equals("check") && value == '\n') {
                        appendBlock(result, kind, segment, checked);
                        kind = heading ? "heading" : "text";
                    }
                    segment.append(value);
                }
            }
            offset = transition;
        }
        appendBlock(result, kind, segment, checked);
        if (result.isEmpty()) result.add(new JournalStore.Block("text", ""));
        return result;
    }

    private static void appendBlock(List<JournalStore.Block> result, String kind, StringBuilder text, boolean checked) {
        if (text.length() == 0 && !kind.equals("check")) return;
        JournalStore.Block block = new JournalStore.Block(kind, text.toString());
        block.checked = kind.equals("check") && checked;
        result.add(block);
        text.setLength(0);
    }

    void insertMedia(JournalStore.Block block, int offset) {
        Editable text = getText();
        int insert = Math.max(0, Math.min(offset, text.length()));
        SpannableStringBuilder value = new SpannableStringBuilder();
        appendObject(value, new MediaSpan(block));
        text.insert(insert, value);
        setSelection(insert + 1);
    }

    void insertChecklist() {
        Editable text = getText();
        int cursor = Math.max(0, getSelectionStart());
        int start = cursor;
        while (start > 0 && text.charAt(start - 1) != '\n' && objectAt(start - 1, MediaSpan.class) == null) start--;
        CheckSpan current = start < text.length() ? objectAt(start, CheckSpan.class) : null;
        if (current != null) {
            text.delete(start, start + 1);
            return;
        }
        SpannableStringBuilder marker = new SpannableStringBuilder();
        appendObject(marker, new CheckSpan(false));
        text.insert(start, marker);
        setSelection(cursor + 1);
    }

    void formatParagraph(boolean heading) {
        Editable text = getText();
        int start = Math.max(0, Math.min(getSelectionStart(), getSelectionEnd()));
        int end = Math.max(start, Math.max(getSelectionStart(), getSelectionEnd()));
        while (start > 0 && text.charAt(start - 1) != '\n') start--;
        while (end < text.length() && text.charAt(end) != '\n') end++;
        if (start == end) return;
        for (Heading span : text.getSpans(start, end, Heading.class)) {
            int from = text.getSpanStart(span);
            int to = text.getSpanEnd(span);
            text.removeSpan(span);
            if (from < start) text.setSpan(new Heading(), from, start, EXCLUSIVE);
            if (to > end) text.setSpan(new Heading(), end, to, EXCLUSIVE);
        }
        if (heading) text.setSpan(new Heading(), start, end, EXCLUSIVE);
    }

    private static void appendObject(SpannableStringBuilder text, ReplacementSpan span) {
        int start = text.length();
        text.append(OBJECT);
        text.setSpan(span, start, start + 1, EXCLUSIVE);
    }

    private <T> T objectAt(int offset, Class<T> type) {
        Editable text = getText();
        if (offset < 0 || offset >= text.length() || text.charAt(offset) != OBJECT) return null;
        for (T span : text.getSpans(offset, offset + 1, type)) {
            if (text.getSpanStart(span) == offset && text.getSpanEnd(span) == offset + 1) return span;
        }
        return null;
    }

    @Override public boolean onTextContextMenuItem(int id) {
        if (id == android.R.id.cut || id == android.R.id.copy) {
            int start = Math.min(getSelectionStart(), getSelectionEnd());
            int end = Math.max(getSelectionStart(), getSelectionEnd());
            if (start >= 0 && end > start) {
                String plain = getText().subSequence(start, end).toString().replace(String.valueOf(OBJECT), "");
                getContext().getSystemService(ClipboardManager.class).setPrimaryClip(ClipData.newPlainText(null, plain));
                if (id == android.R.id.cut && !readOnly) getText().delete(start, end);
                setSelection(start);
                return true;
            }
        }
        return super.onTextContextMenuItem(id);
    }

    @Override public boolean onTouchEvent(MotionEvent event) {
        if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
            downX = event.getX();
            downY = event.getY();
            downTime = event.getEventTime();
        }
        if (event.getActionMasked() == MotionEvent.ACTION_UP
            && event.getEventTime() - downTime < android.view.ViewConfiguration.getLongPressTimeout()
            && Math.abs(event.getX() - downX) < slop && Math.abs(event.getY() - downY) < slop
            && getSelectionStart() == getSelectionEnd() && tapObject(event)) {
            MotionEvent cancelled = MotionEvent.obtain(event);
            cancelled.setAction(MotionEvent.ACTION_CANCEL);
            super.onTouchEvent(cancelled);
            cancelled.recycle();
            return true;
        }
        return super.onTouchEvent(event);
    }

    private boolean tapObject(MotionEvent event) {
        if (getLayout() == null) return false;
        float x = event.getX() - getTotalPaddingLeft() + getScrollX();
        float y = event.getY() - getTotalPaddingTop() + getScrollY();
        Editable text = getText();
        for (MediaSpan span : text.getSpans(0, text.length(), MediaSpan.class)) {
            if (span.block.kind.equals("video") && span.bounds.contains(x, y)) {
                videoAction.open(span);
                return true;
            }
        }
        if (!readOnly) for (CheckSpan span : text.getSpans(0, text.length(), CheckSpan.class)) {
            if (span.bounds.contains(x, y)) {
                int start = text.getSpanStart(span);
                SpannableStringBuilder replacement = new SpannableStringBuilder();
                appendObject(replacement, new CheckSpan(!span.checked));
                text.replace(start, start + 1, replacement);
                return true;
            }
        }
        return false;
    }

    int dp(float size) { return Math.round(size * getResources().getDisplayMetrics().density); }

    @Override protected void onMeasure(int width, int height) {
        availableWidth = MeasureSpec.getSize(width) - getCompoundPaddingLeft() - getCompoundPaddingRight();
        super.onMeasure(width, height);
    }

    @Override protected void onDetachedFromWindow() {
        previews.shutdownNow();
        super.onDetachedFromWindow();
    }

    private void requestBitmap(String name) {
        if (previews.isShutdown() || unavailable.contains(name) || !loading.add(name)) return;
        previews.execute(() -> {
            BitmapFactory.Options options = new BitmapFactory.Options();
            options.inJustDecodeBounds = true;
            String path = new File(media, name).getPath();
            BitmapFactory.decodeFile(path, options);
            options.inSampleSize = 1;
            while (Math.max(options.outWidth, options.outHeight) / options.inSampleSize > 1000) {
                options.inSampleSize *= 2;
            }
            options.inJustDecodeBounds = false;
            Bitmap image = BitmapFactory.decodeFile(path, options);
            post(() -> {
                loading.remove(name);
                if (image == null) unavailable.add(name);
                else bitmaps.put(name, image);
                invalidate();
            });
        });
    }

    private static final class Heading extends android.text.style.MetricAffectingSpan {
        private void apply(android.text.TextPaint paint) {
            android.graphics.Typeface family = paint.getTypeface();
            paint.setTypeface(android.graphics.Typeface.create(family, android.graphics.Typeface.BOLD));
            paint.setTextSize(paint.getTextSize() * 1.3f);
        }

        @Override public void updateDrawState(android.text.TextPaint paint) { apply(paint); }
        @Override public void updateMeasureState(android.text.TextPaint paint) { apply(paint); }
    }

    final class MediaSpan extends ReplacementSpan {
        final JournalStore.Block block;
        final RectF bounds = new RectF();

        MediaSpan(JournalStore.Block block) { this.block = block; }
        private int height() { return dp(block.kind.equals("video") ? 205 : 180); }

        @Override public int getSize(Paint paint, CharSequence text, int start, int end, Paint.FontMetricsInt fm) {
            if (fm != null) {
                fm.ascent = fm.top = -height();
                fm.descent = fm.bottom = dp(5);
            }
            return Math.max(dp(42), availableWidth);
        }

        @Override public void draw(Canvas canvas, CharSequence text, int start, int end, float x,
                                   int top, int baseline, int bottom, Paint paint) {
            bounds.set(x, baseline - height(), x + getSize(paint, text, start, end, null), baseline);
            Paint ink = new Paint(paint);
            ink.setColor(PANEL);
            canvas.drawRoundRect(bounds, dp(10), dp(10), ink);
            if (block.kind.equals("image")) {
                Bitmap image = bitmaps.get(block.file);
                if (image == null) {
                    requestBitmap(block.file);
                } else {
                    float scale = Math.min(bounds.width() / image.getWidth(), bounds.height() / image.getHeight());
                    float width = image.getWidth() * scale;
                    float height = image.getHeight() * scale;
                    RectF destination = new RectF(bounds.centerX() - width / 2, bounds.centerY() - height / 2,
                        bounds.centerX() + width / 2, bounds.centerY() + height / 2);
                    ink.setFilterBitmap(true);
                    canvas.drawBitmap(image, null, destination, ink);
                    return;
                }
            }
            String label = block.kind.equals("video") ? "播放视频" : block.text;
            ink.setColor(FOREST);
            ink.setTextAlign(Paint.Align.CENTER);
            canvas.drawText(label, bounds.centerX(), bounds.centerY(), ink);
        }
    }

    final class CheckSpan extends ReplacementSpan {
        final boolean checked;
        final RectF bounds = new RectF();
        CheckSpan(boolean checked) { this.checked = checked; }

        @Override public int getSize(Paint paint, CharSequence text, int start, int end, Paint.FontMetricsInt fm) {
            return dp(28);
        }

        @Override public void draw(Canvas canvas, CharSequence text, int start, int end, float x,
                                   int top, int baseline, int bottom, Paint paint) {
            bounds.set(x, top, x + dp(26), bottom);
            Paint ink = new Paint(paint);
            ink.setColor(FOREST);
            canvas.drawText(checked ? "☑" : "☐", x, baseline, ink);
        }
    }
}
