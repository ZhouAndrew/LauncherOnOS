package org.qosp.notes.ui.utils

import android.content.Context
import android.net.Uri
import java.io.File
import java.io.IOException
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream
import org.qosp.notes.data.model.Attachment
import org.qosp.notes.ui.attachments.uri
import org.commonmark.ext.gfm.tables.TablesExtension
import org.commonmark.node.AbstractVisitor
import org.commonmark.node.Image
import org.commonmark.node.Link
import org.commonmark.parser.Parser
import java.net.URI
import org.commonmark.renderer.html.HtmlRenderer
import org.qosp.notes.data.model.Note

internal object NoteDocument {
    private val tables = listOf(TablesExtension.create())
    private val parser = Parser.builder().extensions(tables).build()
    private val renderer = HtmlRenderer.builder().extensions(tables)
        .escapeHtml(true).build()

    private fun safeDestination(destination: String): String {
        val url = runCatching { URI(destination) }.getOrNull() ?: return ""
        return when (url.scheme?.lowercase()) {
            null -> if (url.rawAuthority == null) destination else ""
            "https", "http", "mailto" -> destination
            else -> ""
        }
    }

    private fun renderMarkdown(body: String): String {
        val document = parser.parse(body)
        document.accept(object : AbstractVisitor() {
            override fun visit(link: Link) {
                link.destination = safeDestination(link.destination)
                visitChildren(link)
            }

            override fun visit(image: Image) {
                image.destination = safeDestination(image.destination)
                visitChildren(image)
            }
        })
        return renderer.render(document)
    }

    fun filename(title: String, extension: String): String {
        val name = title.replace(Regex("[^\\p{L}\\p{N} _.-]"), "_")
            .take(60).trim(' ', '.').ifBlank { "note" }
        return "$name.$extension"
    }

    fun write(context: Context, destination: Uri, note: Note, html: Boolean, packaged: Boolean) {
        val resolver = context.contentResolver
        val assets = note.attachments.mapIndexed { index, attachment ->
            val extension = attachment.fileName.ifBlank { attachment.description }.substringAfterLast('.', "")
                .takeIf { it.matches(Regex("[A-Za-z0-9]{1,12}")) }
            val path = "attachments/${index + 1}" + (extension?.let { ".$it" } ?: "")
            path to attachment
        }
        if (!packaged) {
            if (assets.isNotEmpty()) throw IOException("Attachments require a ZIP export")
            val output = resolver.openOutputStream(destination, "wt")
                ?: throw IOException("Cannot open export destination")
            output.bufferedWriter(Charsets.UTF_8).use { it.write(from(note, html)) }
            return
        }

        val archive = File.createTempFile("journal-export-", ".zip", context.cacheDir)
        try {
            ZipOutputStream(archive.outputStream().buffered()).use { zip ->
                zip.putNextEntry(ZipEntry(if (html) "note.html" else "note.md"))
                zip.write(from(note, html, assets).toByteArray(Charsets.UTF_8))
                zip.closeEntry()
                for ((path, attachment) in assets) {
                    val source = attachment.uri(context)?.let { resolver.openInputStream(it) }
                        ?: throw IOException("Cannot open attachment")
                    source.use {
                        zip.putNextEntry(ZipEntry(path))
                        it.copyTo(zip)
                        zip.closeEntry()
                    }
                }
            }
            val output = resolver.openOutputStream(destination, "wt")
                ?: throw IOException("Cannot open export destination")
            output.use { target -> archive.inputStream().use { it.copyTo(target) } }
        } finally {
            archive.delete()
        }
    }

    private fun from(note: Note, html: Boolean, assets: List<Pair<String, Attachment>> = emptyList()): String {
        fun renderAsset(asset: Pair<String, Attachment>): String {
            val (path, attachment) = asset
            val label = attachment.description.ifBlank { attachment.fileName }.ifBlank { path }
                .lineSequence().joinToString(" ")
            return if (html) {
                val text = escapeHtml(label)
                when (attachment.type) {
                    Attachment.Type.IMAGE -> "<figure><img src=\"$path\" alt=\"$text\" style=\"max-width:100%\"><figcaption>$text</figcaption></figure>"
                    Attachment.Type.AUDIO -> "<p><audio controls src=\"$path\"></audio> <a href=\"$path\">$text</a></p>"
                    Attachment.Type.VIDEO -> "<p><video controls src=\"$path\" style=\"max-width:100%\"></video> <a href=\"$path\">$text</a></p>"
                    Attachment.Type.GENERIC -> "<p><a href=\"$path\">$text</a></p>"
                }
            } else {
                val image = if (attachment.type == Attachment.Type.IMAGE) "!" else ""
                "$image[${escapeMarkdown(label)}]($path)"
            }
        }
        val title = note.title.lineSequence().joinToString(" ").trim()
        val body = note.toStorableContent()
        val byId = assets.associateBy { InlineMedia.id(it.second) }
        val used = InlineMedia.marker.findAll(body).map { it.groupValues[1] }.toSet()
        val attachments = assets.filterNot { InlineMedia.id(it.second) in used }
            .joinToString(if (html) "\n" else "\n\n", transform = ::renderAsset)
        fun renderText(text: String): String =
            if (note.isMarkdownEnabled) renderMarkdown(text)
            else "<div style=\"white-space:pre-wrap\">${escapeHtml(text)}</div>"
        if (!html) {
            val heading = if (title.isBlank()) "" else "# ${escapeMarkdown(title)}\n\n"
            return heading + InlineMedia.marker.replace(body) { byId[it.groupValues[1]]?.let(::renderAsset).orEmpty() } + if (attachments.isEmpty()) "" else "\n\n$attachments\n"
        }

        val escapedTitle = escapeHtml(title)
        val heading = if (title.isBlank()) "" else "<h1>$escapedTitle</h1>"
        val content = when {
            note.isList -> note.taskList.joinToString("", "<ul>", "</ul>") { task ->
                val checked = if (task.isDone) " checked" else ""
                "<li><input type=\"checkbox\" disabled$checked> ${escapeHtml(task.content)}</li>"
            }
            else -> buildString {
                var start = 0
                for (match in InlineMedia.marker.findAll(body)) {
                    append(renderText(body.substring(start, match.range.first)))
                    byId[match.groupValues[1]]?.let { append(renderAsset(it)) }
                    start = match.range.last + 1
                }
                append(renderText(body.substring(start)))
            }
        }
        return """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>$escapedTitle</title>
</head>
<body>
$heading
$content
$attachments
</body>
</html>
"""
    }

    private fun escapeMarkdown(text: String): String = buildString {
        text.forEach { char ->
            if (char in "\\`*_{}[]<>()#+-.!|&") append('\\')
            append(char)
        }
    }

    private fun escapeHtml(text: String): String = text.replace("&", "&amp;")
        .replace("<", "&lt;").replace(">", "&gt;").replace("\"", "&quot;")
}
