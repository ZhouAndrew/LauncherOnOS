package org.qosp.notes.ui.utils

import java.util.UUID
import org.qosp.notes.data.model.Attachment

internal object InlineMedia {
    val marker = Regex("(?m)^\\[journal-media:([a-f0-9-]{36})]$")
    fun id(attachment: Attachment): String =
        UUID.nameUUIDFromBytes(attachment.path.toByteArray(Charsets.UTF_8)).toString()

    fun insert(body: String, offset: Int, attachments: List<Attachment>): String {
        val media = attachments.filter { it.type == Attachment.Type.IMAGE || it.type == Attachment.Type.VIDEO }
        if (media.isEmpty()) return body
        val index = if (offset < 0) body.length else offset.coerceAtMost(body.length)
        return body.substring(0, index) + "\n\n" +
            media.joinToString("\n\n") { "[journal-media:${id(it)}]" } +
            "\n\n" + body.substring(index)
    }
}
