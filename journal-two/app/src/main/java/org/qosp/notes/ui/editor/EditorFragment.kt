package org.qosp.notes.ui.editor

import android.Manifest
import android.app.AlarmManager
import android.content.Context
import android.content.ActivityNotFoundException
import android.content.pm.PackageManager
import android.location.LocationManager
import androidx.core.content.ContextCompat
import androidx.core.location.LocationManagerCompat
import androidx.core.os.CancellationSignal
import android.content.Intent
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.net.Uri
import android.os.Build
import android.os.Bundle
import android.provider.Settings
import android.speech.RecognizerIntent
import android.speech.RecognitionListener
import android.speech.SpeechRecognizer
import android.view.MotionEvent
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.util.Log
import android.view.ContextThemeWrapper
import android.view.Menu
import android.view.MenuInflater
import android.view.MenuItem
import android.view.View
import android.view.WindowManager
import android.view.inputmethod.EditorInfo
import android.widget.TextView
import androidx.activity.addCallback
import androidx.activity.result.contract.ActivityResultContracts
import androidx.annotation.ColorInt
import androidx.appcompat.widget.Toolbar
import androidx.constraintlayout.widget.ConstraintLayout
import androidx.core.graphics.drawable.toBitmap
import androidx.core.view.ViewCompat
import androidx.core.view.doOnNextLayout
import androidx.core.view.doOnPreDraw
import androidx.core.view.isVisible
import androidx.core.view.marginBottom
import androidx.core.view.updateLayoutParams
import androidx.core.widget.doOnTextChanged
import androidx.fragment.app.clearFragmentResult
import androidx.fragment.app.setFragmentResultListener
import androidx.lifecycle.lifecycleScope
import androidx.navigation.fragment.findNavController
import androidx.navigation.fragment.navArgs
import androidx.recyclerview.widget.ItemTouchHelper
import androidx.recyclerview.widget.ItemTouchHelper.ACTION_STATE_DRAG
import androidx.recyclerview.widget.ItemTouchHelper.ACTION_STATE_SWIPE
import androidx.recyclerview.widget.ItemTouchHelper.DOWN
import androidx.recyclerview.widget.ItemTouchHelper.LEFT
import androidx.recyclerview.widget.ItemTouchHelper.RIGHT
import androidx.recyclerview.widget.ItemTouchHelper.UP
import androidx.recyclerview.widget.LinearLayoutManager
import androidx.recyclerview.widget.RecyclerView
import com.google.android.material.snackbar.BaseTransientBottomBar
import com.google.android.material.snackbar.Snackbar
import com.google.android.material.transition.MaterialContainerTransform
import com.google.android.material.transition.MaterialSharedAxis
import io.noties.markwon.Markwon
import io.noties.markwon.editor.MarkwonEditor
import io.noties.markwon.editor.MarkwonEditorTextWatcher
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import org.commonmark.node.Code
import org.qosp.notes.ui.utils.NoteDocument
import java.io.IOException
import java.io.File
import java.util.UUID
import org.koin.android.ext.android.inject
import org.koin.androidx.viewmodel.ext.android.viewModel
import org.qosp.notes.App
import org.qosp.notes.R
import org.qosp.notes.data.model.Attachment
import org.qosp.notes.data.model.Note
import org.qosp.notes.data.model.NoteColor
import org.qosp.notes.data.model.NoteTask
import org.qosp.notes.databinding.FragmentEditorBinding
import org.qosp.notes.databinding.LayoutAttachmentBinding
import org.qosp.notes.preferences.DefaultEditorMode
import org.qosp.notes.ui.attachments.dialog.EditAttachmentDialog
import org.qosp.notes.ui.attachments.fromUri
import org.qosp.notes.ui.attachments.getAttachmentUri
import org.qosp.notes.ui.attachments.recycler.AttachmentRecyclerListener
import org.qosp.notes.ui.attachments.recycler.AttachmentsAdapter
import org.qosp.notes.ui.attachments.recycler.AttachmentsGridManager
import org.qosp.notes.ui.attachments.uri
import org.qosp.notes.ui.common.BaseDialog
import org.qosp.notes.ui.common.BaseFragment
import org.qosp.notes.ui.common.showMoveToNotebookDialog
import org.qosp.notes.ui.editor.dialog.InsertHyperlinkDialog
import org.qosp.notes.ui.editor.dialog.InsertImageDialog
import org.qosp.notes.ui.editor.dialog.InsertTableDialog
import org.qosp.notes.ui.editor.markdown.MarkdownSpan
import org.qosp.notes.ui.editor.markdown.applyTo
import org.qosp.notes.ui.editor.markdown.insertMarkdown
import org.qosp.notes.ui.editor.markdown.toggleCheckmarkCurrentLine
import org.qosp.notes.ui.media.MediaActivity
import org.qosp.notes.ui.recorder.RECORDED_ATTACHMENT
import org.qosp.notes.ui.recorder.RECORD_CODE
import org.qosp.notes.ui.recorder.RecordAudioDialog
import org.qosp.notes.ui.reminders.EditReminderDialog
import org.qosp.notes.ui.tasks.TaskRecyclerListener
import org.qosp.notes.ui.tasks.TaskViewHolder
import org.qosp.notes.ui.tasks.TasksAdapter
import org.qosp.notes.ui.utils.ChooseFilesContract
import org.qosp.notes.ui.utils.HighQualityVideoContract
import org.qosp.notes.ui.utils.InlineMedia
import android.text.method.LinkMovementMethod
import android.text.util.Linkify
import android.widget.Button
import android.widget.ImageView
import android.widget.MediaController
import android.widget.VideoView
import coil.load
import org.qosp.notes.ui.utils.views.ExtendedEditText
import org.qosp.notes.ui.utils.TakePictureContract
import org.qosp.notes.ui.utils.collect
import org.qosp.notes.ui.utils.dp
import org.qosp.notes.ui.utils.getDimensionAttribute
import org.qosp.notes.ui.utils.getDrawableCompat
import org.qosp.notes.ui.utils.hideKeyboard
import org.qosp.notes.ui.utils.liftAppBarOnScroll
import org.qosp.notes.ui.utils.navigateSafely
import org.qosp.notes.ui.utils.requestFocusAndKeyboard
import org.qosp.notes.ui.utils.resId
import org.qosp.notes.ui.utils.resolveAttribute
import org.qosp.notes.ui.utils.shareAttachment
import org.qosp.notes.ui.utils.shareNote
import org.qosp.notes.ui.utils.viewBinding
import org.qosp.notes.ui.utils.views.BottomSheet
import org.qosp.notes.ui.widget.WidgetUpdateHelper
import java.time.Instant
import java.time.LocalDateTime
import java.time.ZoneId
import java.time.format.DateTimeFormatter
import java.util.concurrent.Executors

private typealias Data = EditorViewModel.Data

class EditorFragment : BaseFragment(R.layout.fragment_editor) {
    private val binding by viewBinding(FragmentEditorBinding::bind)
    private val model: EditorViewModel by viewModel()

    private val args: EditorFragmentArgs by navArgs()
    private var snackbar: Snackbar? = null
    private var mainMenu: Menu? = null
    private var contentHasFocus: Boolean = false
    private var isNoteDeleted: Boolean = false
    private var markwonTextWatcher: TextWatcher? = null
    private var onBackPressHandled: Boolean = false

    @ColorInt
    private var backgroundColor: Int = Color.TRANSPARENT
    private var data = Data()

    private var nextTaskId: Long = 0L
    private var isList: Boolean = false
    private var isFirstLoad: Boolean = true
    private var formatter: DateTimeFormatter? = null

    private lateinit var attachmentsAdapter: AttachmentsAdapter
    private lateinit var tasksAdapter: TasksAdapter

    val markwon: Markwon by inject()

    val markwonEditor: MarkwonEditor by inject()

    override val hasDefaultAnimation = false
    override val toolbar: Toolbar
        get() = binding.toolbar

    private var previewedNote: Note? = null
    private var previewWasEditable = false
    private val bodyFields = mutableListOf<ExtendedEditText>()
    private var activeBodyField: ExtendedEditText? = null

    private fun bodyOffset(): Int {
        if (!model.inEditMode) return -1
        val field = activeBodyField ?: return binding.editTextContent.selectionEnd
        val index = bodyFields.indexOf(field)
        if (index < 0) return -1
        val marker = InlineMedia.marker.findAll(binding.editTextContent.text.toString()).take(index).lastOrNull()
        return (marker?.range?.last?.plus(1) ?: 0) + field.selectionEnd.coerceAtLeast(0)
    }

    private fun replaceBody(content: String, cursor: Int) {
        binding.editTextContent.withOnlyTextWatcher<MarkwonEditorTextWatcher> { setText(content) }
        binding.editTextContent.setSelection(cursor.coerceIn(0, content.length))
        val note = data.note ?: return
        renderBodyPreview(note.copy(content = content))
        focusBody(cursor)
    }

    private fun focusBody(cursor: Int) {
        if (bodyFields.isEmpty()) return
        val markers = InlineMedia.marker.findAll(binding.editTextContent.text.toString()).toList()
        val index = markers.count { it.range.first < cursor }.coerceAtMost(bodyFields.lastIndex)
        val start = markers.getOrNull(index - 1)?.range?.last?.plus(1) ?: 0
        val field = bodyFields[index]
        field.requestFocus()
        field.setSelection((cursor - start).coerceIn(0, field.length()))
    }

    private fun insertBodyText(offset: Int, text: String) {
        val before = binding.editTextContent.text.toString()
        val cursor = offset.takeIf { it in 0..before.length } ?: before.length
        val after = before.substring(0, cursor) + text + before.substring(cursor)
        replaceBody(after, cursor + text.length)
        model.setNoteContent(after)
    }
    private var inlinePlayer: VideoView? = null
    private var locationRequest: CancellationSignal? = null

    private var recognizer: SpeechRecognizer? = null
    private var dictationHeld = false
    private var dictationOffset = -1
    private var dictationResult: String? = null
    private var dictationCancelled = false

    private val microphonePermission =
        registerForActivityResult(ActivityResultContracts.RequestPermission()) { granted ->
            if (granted) sendMessage(getString(R.string.journal_hold_to_dictate))
        }

    private fun cancelDictation() {
        recognizer?.destroy()
        recognizer = null
        dictationHeld = false
        dictationResult = null
    }

    private fun finishDictation(text: String?) {
        cancelDictation()
        if (!text.isNullOrBlank() && view != null && data.note?.isDeleted == false) {
            updateEditMode(true)
            insertBodyText(dictationOffset, text)
        }
    }

    private fun startDictation() {
        val context = requireContext()
        if (ContextCompat.checkSelfPermission(context, Manifest.permission.RECORD_AUDIO) !=
            PackageManager.PERMISSION_GRANTED) {
            microphonePermission.launch(Manifest.permission.RECORD_AUDIO)
            return
        }
        if (!SpeechRecognizer.isRecognitionAvailable(context)) {
            sendMessage(getString(R.string.journal_dictation_unavailable))
            return
        }
        cancelDictation()
        dictationHeld = true
        dictationOffset = bodyOffset()
        val session = SpeechRecognizer.createSpeechRecognizer(context)
        recognizer = session
        session.setRecognitionListener(object : RecognitionListener {
            override fun onReadyForSpeech(params: Bundle?) = Unit
            override fun onBeginningOfSpeech() = Unit
            override fun onRmsChanged(rmsdB: Float) = Unit
            override fun onBufferReceived(buffer: ByteArray?) = Unit
            override fun onEndOfSpeech() = Unit
            override fun onPartialResults(partialResults: Bundle?) = Unit
            override fun onEvent(eventType: Int, params: Bundle?) = Unit
            override fun onError(error: Int) {
                if (recognizer !== session) return
                cancelDictation()
                if (view != null) sendMessage(getString(R.string.journal_dictation_failed))
            }
            override fun onResults(results: Bundle?) {
                if (recognizer !== session) return
                val text = results?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)?.firstOrNull()
                if (dictationHeld) dictationResult = text.orEmpty() else finishDictation(text)
            }
        })
        session.startListening(Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
            .putExtra(RecognizerIntent.EXTRA_LANGUAGE, resources.configuration.locales[0].toLanguageTag())
            .putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1))
    }

    private fun bindDictationGesture() {
        toolbar.post {
            if (view == null) return@post
            val button = toolbar.findViewById<View>(R.id.action_journal_dictation) ?: return@post
            var startY = 0f
            button.setOnTouchListener { _, event ->
                when (event.actionMasked) {
                    MotionEvent.ACTION_DOWN -> {
                        startY = event.rawY
                        dictationCancelled = false
                        startDictation()
                        button.isPressed = recognizer != null
                        if (button.isPressed) sendMessage(getString(R.string.journal_slide_to_cancel))
                    }
                    MotionEvent.ACTION_MOVE -> {
                        dictationCancelled = startY - event.rawY > 56.dp(button.context)
                        button.isPressed = recognizer != null && !dictationCancelled
                    }
                    MotionEvent.ACTION_UP -> {
                        button.isPressed = false
                        if (dictationCancelled) cancelDictation()
                        else if (recognizer != null) {
                            dictationHeld = false
                            val pending = dictationResult
                            if (pending != null) finishDictation(pending) else recognizer?.stopListening()
                        }
                    }
                    MotionEvent.ACTION_CANCEL -> {
                        button.isPressed = false
                        cancelDictation()
                    }
                }
                true
            }
        }
    }

    private val locationPermission =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { result ->
            if (result.values.any { it }) addCurrentLocation()
            else sendMessage(getString(R.string.location_unavailable))
        }

    private fun addCurrentLocation() {
        if (data.note?.let { it.isList || it.isDeleted } != false) return
        val context = requireContext()
        val fine = Manifest.permission.ACCESS_FINE_LOCATION
        val coarse = Manifest.permission.ACCESS_COARSE_LOCATION
        val precise = ContextCompat.checkSelfPermission(context, fine) == PackageManager.PERMISSION_GRANTED
        if (!precise && ContextCompat.checkSelfPermission(context, coarse) != PackageManager.PERMISSION_GRANTED) {
            locationPermission.launch(arrayOf(fine, coarse))
            return
        }

        val manager = context.getSystemService(Context.LOCATION_SERVICE) as LocationManager
        val providers = if (precise) listOf(LocationManager.GPS_PROVIDER, LocationManager.NETWORK_PROVIDER)
            else listOf(LocationManager.NETWORK_PROVIDER)
        val provider = providers.firstOrNull { manager.isProviderEnabled(it) }
        if (provider == null) {
            sendMessage(getString(R.string.location_unavailable))
            return
        }
        locationRequest?.cancel()
        val request = CancellationSignal()
        locationRequest = request
        try {
            LocationManagerCompat.getCurrentLocation(manager, provider, request,
                ContextCompat.getMainExecutor(context)) { location ->
                if (locationRequest !== request || view == null) return@getCurrentLocation
                locationRequest = null
                if (location == null) {
                    sendMessage(getString(R.string.location_unavailable))
                    return@getCurrentLocation
                }
                val note = data.note ?: return@getCurrentLocation
                if (note.isList || note.isDeleted) return@getCurrentLocation
                val coordinates = "${location.latitude}/${location.longitude}"
                val url = "https://www.openstreetmap.org/?mlat=${location.latitude}&mlon=${location.longitude}#map=16/$coordinates"
                val label = getString(R.string.note_location)
                val link = if (note.isMarkdownEnabled) "[$label]($url)" else "$label $url"
                insertBodyText(bodyOffset(), "\n\n$link\n\n")
            }
        } catch (error: SecurityException) {
            locationRequest = null
            sendMessage(getString(R.string.location_unavailable))
        }
    }

    private val saveMarkdownDocument =
        registerForActivityResult(ActivityResultContracts.CreateDocument("text/markdown")) {
            saveNoteDocument(it, html = false)
        }

    private val saveHtmlDocument =
        registerForActivityResult(ActivityResultContracts.CreateDocument("text/html")) {
            saveNoteDocument(it, html = true)
        }

    private val saveMarkdownPackage =
        registerForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) {
            saveNoteDocument(it, html = false, packaged = true)
        }

    private val saveHtmlPackage =
        registerForActivityResult(ActivityResultContracts.CreateDocument("application/zip")) {
            saveNoteDocument(it, html = true, packaged = true)
        }

    private fun saveNoteDocument(uri: Uri?, html: Boolean, packaged: Boolean = false) {
        if (uri == null) return
        val context = requireContext().applicationContext
        lifecycleScope.launch {
            val note = model.savedNote() ?: return@launch
            val saved = withContext(Dispatchers.IO) {
                try {
                    NoteDocument.write(context, uri, note, html, packaged)
                    true
                } catch (error: IOException) {
                    Log.w(TAG, "Could not write note document", error)
                    false
                } catch (error: SecurityException) {
                    Log.w(TAG, "Could not access note document", error)
                    false
                }
            }
            sendMessage(getString(if (saved) R.string.note_exported else R.string.note_export_failed))
        }
    }

    private val requestMediaLauncher = registerForActivityResult(ChooseFilesContract) { uris ->
        if (uris.isEmpty()) return@registerForActivityResult
        val context = requireContext().applicationContext
        val offset = mediaOffset
        viewLifecycleOwner.lifecycleScope.launch {
            try {
                val attachments = withContext(Dispatchers.IO) {
                    uris.distinct().map { uri -> copyOriginal(context, uri) }
                }
                insertMedia(attachments, offset)
            } catch (error: IOException) {
                Log.w(TAG, "Could not copy original media", error)
                sendMessage(getString(R.string.journal_import_media_failed))
            } catch (error: SecurityException) {
                Log.w(TAG, "Could not read original media", error)
                sendMessage(getString(R.string.journal_import_media_failed))
            }
        }
    }

    private fun copyOriginal(context: Context, uri: Uri): Attachment {
        val attachment = Attachment.fromUri(context, uri)
        val mimeType = context.contentResolver.getType(uri)
        val extension = attachment.description.substringAfterLast('.', "")
            .takeIf { it.matches(Regex("[A-Za-z0-9]{1,12}")) }
            ?: android.webkit.MimeTypeMap.getSingleton().getExtensionFromMimeType(mimeType)
        val name = UUID.randomUUID().toString() + (extension?.let { ".$it" } ?: "")
        val directory = File(context.filesDir, App.MEDIA_FOLDER).also { it.mkdirs() }
        val file = File(directory, name)
        try {
            val source = context.contentResolver.openInputStream(uri) ?: throw IOException("Cannot read media")
            source.use { input -> file.outputStream().use { output -> input.copyTo(output) } }
        } catch (error: Exception) {
            file.delete()
            throw error
        }
        return attachment.copy(path = name, fileName = name)
    }

    private fun insertMedia(attachments: List<Attachment>, offset: Int = mediaOffset) {
        val editor = binding.editTextContent
        val before = editor.text.toString()
        val after = InlineMedia.insert(before, offset, attachments)
        model.insertAttachments(*attachments.toTypedArray(), content = after)
        if (!isList && after != before) {
            val insertion = if (offset < 0) before.length else offset.coerceAtMost(before.length)
            val cursor = insertion + after.length - before.length
            editor.withOnlyTextWatcher<MarkwonEditorTextWatcher> { setText(after) }
            editor.setSelection(cursor)
            data.note?.let { renderBodyPreview(it.copy(content = after, attachments = it.attachments + attachments)) }
            focusBody(cursor)
        }
    }

    private var pendingVideo: String? = null
    private var mediaOffset = -1

    private val recordVideo =
        registerForActivityResult(HighQualityVideoContract) { saved ->
            val filename = pendingVideo ?: return@registerForActivityResult
            pendingVideo = null
            val file = File(File(requireContext().filesDir, App.MEDIA_FOLDER), filename)
            if (!saved || file.length() == 0L) {
                file.delete()
                if (saved) sendMessage(getString(R.string.record_video_failed))
                return@registerForActivityResult
            }
            insertMedia(listOf(Attachment(
                type = Attachment.Type.VIDEO,
                path = filename,
                fileName = filename,
                description = getString(R.string.action_record_video),
            )))
        }

    private fun startVideoRecording() {
        if (pendingVideo != null) return
        val context = requireContext()
        val filename = "video-${UUID.randomUUID()}.mp4"
        val uri = getAttachmentUri(context, filename)
        if (uri == null) {
            sendMessage(getString(R.string.record_video_failed))
            return
        }
        pendingVideo = filename
        try {
            recordVideo.launch(uri)
        } catch (error: ActivityNotFoundException) {
            pendingVideo = null
            sendMessage(getString(R.string.record_video_failed))
        } catch (error: SecurityException) {
            pendingVideo = null
            sendMessage(getString(R.string.record_video_failed))
        }
    }

    private val takePhotoLauncher = registerForActivityResult(TakePictureContract) { saved ->
        if (!saved) return@registerForActivityResult
        val uri = activityModel.tempPhotoUri ?: return@registerForActivityResult

        insertMedia(listOf(Attachment.fromUri(requireContext(), uri)))
        activityModel.tempPhotoUri = null
    }

    private val itemTouchHelper = ItemTouchHelper(object : ItemTouchHelper.SimpleCallback(UP or DOWN, LEFT or RIGHT) {
        override fun isLongPressDragEnabled() = false

        override fun isItemViewSwipeEnabled() = model.inEditMode

        override fun getSwipeThreshold(viewHolder: RecyclerView.ViewHolder) = 0.5F

        override fun getSwipeEscapeVelocity(defaultValue: Float) = 3 * defaultValue

        override fun getSwipeVelocityThreshold(defaultValue: Float) = defaultValue / 3

        override fun onSwiped(viewHolder: RecyclerView.ViewHolder, direction: Int) {
            binding.scrollView.findFocus()?.clearFocus()
            tasksAdapter.tasks.removeAt(viewHolder.bindingAdapterPosition)
            model.updateTaskList(tasksAdapter.tasks)
            tasksAdapter.notifyItemRemoved(viewHolder.bindingAdapterPosition)
            tasksAdapter.notifyItemRangeChanged(viewHolder.bindingAdapterPosition, tasksAdapter.tasks.size - 1)
        }

        override fun onMove(
            recyclerView: RecyclerView,
            viewHolder: RecyclerView.ViewHolder,
            target: RecyclerView.ViewHolder,
        ): Boolean {
            tasksAdapter.moveItem(viewHolder.bindingAdapterPosition, target.bindingAdapterPosition)
            return true
        }

        override fun onChildDraw(
            c: Canvas,
            recyclerView: RecyclerView,
            viewHolder: RecyclerView.ViewHolder,
            dX: Float,
            dY: Float,
            actionState: Int,
            isCurrentlyActive: Boolean,
        ) {
            when (actionState) {
                ACTION_STATE_DRAG -> {
                    val top = viewHolder.itemView.top + dY
                    val bottom = top + viewHolder.itemView.height
                    if (top > 0 && bottom < recyclerView.height) {
                        super.onChildDraw(c, recyclerView, viewHolder, dX, dY, actionState, isCurrentlyActive)
                    }
                }

                ACTION_STATE_SWIPE -> {
                    val newDx = dX / 3
                    val p = Paint().apply { color = context?.resolveAttribute(R.attr.colorTaskSwipe) ?: Color.RED }
                    val itemView = viewHolder.itemView
                    val icon = context?.getDrawableCompat(R.drawable.ic_indicator_delete_task)?.toBitmap()
                    val height = itemView.bottom - itemView.top
                    val size = (24).dp(requireContext())

                    if (dX < 0) {
                        val background = RectF(
                            itemView.right.toFloat() + newDx,
                            itemView.top.toFloat(),
                            itemView.right.toFloat(),
                            itemView.bottom.toFloat()
                        )
                        c.drawRect(background, p)

                        val iconRect = RectF(
                            background.right - size - 16.dp(requireContext()),
                            background.top + (height - size) / 2,
                            background.right - 16.dp(requireContext()),
                            background.bottom - (height - size) / 2,
                        )
                        if (icon != null) c.drawBitmap(icon, null, iconRect, p)
                    } else if (dX > 0) {
                        val background = RectF(
                            itemView.left.toFloat(),
                            itemView.top.toFloat(),
                            newDx,
                            itemView.bottom.toFloat()
                        )
                        c.drawRect(background, p)
                        val iconRect = RectF(
                            background.left + 16.dp(requireContext()),
                            background.top + (height - size) / 2,
                            background.left + size + 16.dp(requireContext()),
                            background.bottom - (height - size) / 2,
                        )
                        if (icon != null) c.drawBitmap(icon, null, iconRect, p)
                    }
                    return super.onChildDraw(c, recyclerView, viewHolder, newDx, dY, actionState, isCurrentlyActive)
                }
            }
        }

        override fun onSelectedChanged(viewHolder: RecyclerView.ViewHolder?, actionState: Int) {
            super.onSelectedChanged(viewHolder, actionState)

            (viewHolder as TaskViewHolder?)?.let { vh ->
                vh.taskBackgroundColor = backgroundColor
                vh.isBeingMoved = true
            }
        }

        override fun clearView(recyclerView: RecyclerView, viewHolder: RecyclerView.ViewHolder) {
            super.clearView(recyclerView, viewHolder)
            (viewHolder as TaskViewHolder?)?.let {
                if (it.isBeingMoved) it.isBeingMoved = false
            }
            model.updateTaskList(tasksAdapter.tasks)
        }
    })

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        pendingVideo = savedInstanceState?.getString("journal.pendingVideo")
        mediaOffset = savedInstanceState?.getInt("journal.mediaOffset", -1) ?: -1
        sharedElementEnterTransition = MaterialContainerTransform().apply {
            drawingViewId = R.id.nav_host_fragment
            duration = 300L
            scrimColor = Color.TRANSPARENT

            requireContext().resolveAttribute(R.attr.colorBackground)?.let { setAllContainerColors(it) }
        }
        reenterTransition = MaterialSharedAxis(MaterialSharedAxis.Z, true).apply { duration = 300L }

        postponeEnterTransition()
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)

        data = Data()
        previewedNote = null
        activeBodyField = null
        bodyFields.clear()
        isFirstLoad = true

        if (model.isNotInitialized) {
            model.initialize(
                noteId = savedInstanceState?.getLong("journal.noteId")?.takeIf { it > 0 } ?: args.noteId,
                newNoteTitle = args.newNoteTitle,
                newNoteContent = args.newNoteContent,
                newNoteAttachments = args.newNoteAttachments?.toList() ?: emptyList(),
                newNoteIsList = args.newNoteIsList,
                newNoteNotebookId = args.newNoteNotebookId.takeIf { it > 0L }
            )
        }

        setupAttachmentsRecycler()
        setupTasksRecycler()
        observeData()
        setupEditTexts()
        setupMarkdown()
        setupListeners()

        toolbar.setTitleTextColor(Color.TRANSPARENT)
        ViewCompat.setTransitionName(binding.root, args.transitionName)
        binding.scrollView.liftAppBarOnScroll(
            binding.layoutAppBar,
            requireContext().resources.getDimension(R.dimen.app_bar_elevation)
        )

        setFragmentResultListener(RECORD_CODE) { _, bundle ->
            val attachment = bundle.getParcelable<Attachment>(RECORDED_ATTACHMENT) ?: return@setFragmentResultListener
            model.insertAttachments(attachment)
        }

        setFragmentResultListener(MARKDOWN_DIALOG_RESULT) { _, bundle ->
            val markdown = bundle.getString(MARKDOWN_DIALOG_RESULT) ?: return@setFragmentResultListener
            (activeBodyField ?: binding.editTextContent).apply {
                if (selectedText?.isNotEmpty() == true) {
                    text?.replace(selectionStart, selectionEnd, "")
                }
                text?.insert(selectionStart, markdown)
            }
        }

        binding.fabChangeMode.setOnClickListener {
            updateEditMode(!model.inEditMode)
            if (model.inEditMode) {
                data.note?.let { renderBodyPreview(it) }
                requestFocusForFields(true)
            } else {
                view.hideKeyboard()
                data.note?.let(::showSavedPreview)
            }
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onCreateOptionsMenu(menu: Menu, inflater: MenuInflater) {
        inflater.inflate(R.menu.editor_top, menu)
        this.mainMenu = menu

        lifecycleScope.launch {
            model.data.first().note?.let { setupMenuItems(it, it.reminders.isNotEmpty()) }
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onOptionsItemSelected(item: MenuItem): Boolean {
        data.note?.let { note ->
            when (item.itemId) {
                R.id.action_convert_note -> {
                    if (note.isList) model.toTextNote() else model.toList()
                }

                R.id.action_archive_note -> {
                    if (note.isArchived) activityModel.unarchiveNotes(note) else activityModel.archiveNotes(note)
                    sendMessage(getString(R.string.indicator_archive_note))
                    activity?.onBackPressedDispatcher?.onBackPressed()
                }

                R.id.action_delete_note -> {
                    activityModel.deleteNotes(note)
                    sendMessage(getString(R.string.indicator_moved_note_to_bin))
                    activity?.onBackPressedDispatcher?.onBackPressed()
                }

                R.id.action_restore_note -> {
                    activityModel.restoreNotes(note)
                    activity?.onBackPressedDispatcher?.onBackPressed()
                }

                R.id.action_delete_permanently_note -> {
                    activityModel.deleteNotesPermanently(note)
                    sendMessage(getString(R.string.indicator_deleted_note_permanently))
                    activity?.onBackPressedDispatcher?.onBackPressed()
                }

                R.id.action_view_tags -> {
                    findNavController().navigateSafely(
                        EditorFragmentDirections.actionEditorToTags().setNoteId(note.id)
                    )
                }

                R.id.action_view_reminders -> {
                    showRemindersDialog(note)
                }

                R.id.action_pin_note -> {
                    activityModel.pinNotes(note)
                    // Refresh widgets to reflect pin state change
                    WidgetUpdateHelper.updateAllWidgets(requireContext())
                }

                R.id.action_change_mode -> {
                    updateEditMode(!model.inEditMode)
                    if (model.inEditMode) {
                        renderBodyPreview(note)
                        requestFocusForFields(true)
                    } else {
                        view?.hideKeyboard()
                        showSavedPreview(note)
                    }
                    setupMenuItems(note, note.reminders.isNotEmpty())
                }

                R.id.action_hide_note -> {
                    if (note.isHidden) activityModel.showNotes(note) else activityModel.hideNotes(note)
                }

                R.id.action_do_not_sync -> {
                    if (note.isLocalOnly) activityModel.makeNotesSyncable(note) else activityModel.makeNotesLocal(note)
                }

                R.id.action_change_color -> {
                    showColorChangeDialog()
                }

                R.id.action_journal_dictation -> {
                    sendMessage(getString(R.string.journal_hold_to_dictate))
                    return true
                }

                R.id.action_add_location -> {
                    addCurrentLocation()
                    return true
                }

                R.id.action_save_markdown -> {
                    if (note.attachments.isEmpty()) {
                        saveMarkdownDocument.launch(NoteDocument.filename(note.title, "md"))
                    } else {
                        saveMarkdownPackage.launch(NoteDocument.filename(note.title, "md.zip"))
                    }
                    return true
                }

                R.id.action_export_wordpress -> {
                    saveHtmlPackage.launch(NoteDocument.filename(note.title, "html.zip"))
                    return true
                }

                R.id.action_save_html -> {
                    if (note.attachments.isEmpty()) {
                        saveHtmlDocument.launch(NoteDocument.filename(note.title, "html"))
                    } else {
                        saveHtmlPackage.launch(NoteDocument.filename(note.title, "html.zip"))
                    }
                    return true
                }

                R.id.action_export_note -> {
                    activityModel.notesToBackup = setOf(note)
                    exportNotesLauncher.launch(null)
                }

                R.id.action_share -> {
                    shareNote(requireContext(), note)
                }

                R.id.action_attach_file -> {
                    mediaOffset = bodyOffset()
                    requestMediaLauncher.launch(null)
                }

                R.id.action_take_photo -> {
                    mediaOffset = bodyOffset()
                    lifecycleScope.launch {
                        runCatching {
                            takePhotoLauncher.launch(activityModel.createImageFile())
                        }.getOrElse { Log.e(TAG, "Cannot launch camera app", it) }
                    }
                }

                R.id.action_record_video -> {
                    mediaOffset = bodyOffset()
                    if (!note.isDeleted) startVideoRecording()
                    return true
                }

                R.id.action_record_audio -> {
                    clearFragmentResult(RECORD_CODE)
                    RecordAudioDialog().show(parentFragmentManager, null)
                }

                R.id.action_enable_disable_markdown -> {
                    if (note.isMarkdownEnabled) {
                        activityModel.disableMarkdown(note)
                    } else {
                        activityModel.enableMarkdown(note)
                    }
                }

                R.id.action_screen_always_on -> {
                    if (note.screenAlwaysOn) {
                        activityModel.disableScreenAlwaysOn(note)
                    } else {
                        activityModel.enableScreenAlwaysOn(note)
                    }
                    setupScreenAlwaysOn(!note.screenAlwaysOn)
                }

                R.id.action_uncheck_all_tasks -> {
                    uncheckAllTasks()
                    true
                }

                R.id.action_remove_all_checked_tasks -> {
                    removeAllCheckedTasks()
                    true
                }

                else -> false
            }
        }
        return super.onOptionsItemSelected(item)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        data.note?.id?.let { outState.putLong("journal.noteId", it) }
        outState.putString("journal.pendingVideo", pendingVideo)
        outState.putInt("journal.mediaOffset", mediaOffset)
    }

    override fun onPause() {
        cancelDictation()
        inlinePlayer?.pause()
        locationRequest?.cancel()
        locationRequest = null
        model.selectedRange = with(binding.editTextContent) { selectionStart to selectionEnd }
        super.onPause()
    }

    override fun onDestroyView() {
        inlinePlayer?.stopPlayback()
        inlinePlayer = null
        // Dismiss the snackbar which is shown for deleted notes
        snackbar?.dismiss()
        itemTouchHelper.attachToRecyclerView(null)
        attachmentsAdapter.listener = null
        tasksAdapter.listener = null
        setupScreenAlwaysOn(false)
        super.onDestroyView()
    }

    private fun jumpToNextTaskOrAdd(fromPosition: Int) {
        val next = tasksAdapter.tasks.getOrNull(fromPosition + 1)
        if (next == null || next.content.isNotEmpty()) {
            addTask(fromPosition + 1)
            return
        }
        (binding.recyclerTasks.findViewHolderForAdapterPosition(fromPosition + 1) as TaskViewHolder).requestFocus()
    }

    private fun setupTasksRecycler() {
        tasksAdapter = TasksAdapter(
            false,
            object : TaskRecyclerListener {
                override fun onDrag(viewHolder: TaskViewHolder) {
                    itemTouchHelper.startDrag(viewHolder)
                }

                override fun onTaskStatusChanged(position: Int, isDone: Boolean) {
                    updateTask(position = position, isDone = isDone)
                }

                override fun onTaskContentChanged(position: Int, content: String) {
                    updateTask(position = position, content = content)
                }

                override fun onNext(position: Int) {
                    jumpToNextTaskOrAdd(position)
                }
            },
            markwon = markwon,
        )

        binding.recyclerTasks.apply {
            isVisible = true
            layoutManager = LinearLayoutManager(context, LinearLayoutManager.VERTICAL, false)
            adapter = tasksAdapter
            itemTouchHelper.attachToRecyclerView(this)
        }
    }

    private fun setupAttachmentsRecycler() = with(binding) {
        // Create the adapter
        val listener = object : AttachmentRecyclerListener {
            override fun onItemClick(position: Int, viewBinding: LayoutAttachmentBinding) {
                val attachment = attachmentsAdapter.getItemAtPosition(position)

                if (data.openMediaInternally) {
                    startActivity(
                        Intent(requireContext(), MediaActivity::class.java).apply {
                            putExtra(MediaActivity.ATTACHMENT, attachment)
                        }
                    )
                } else {
                    Intent(Intent.ACTION_VIEW).apply {
                        data = attachment.uri(requireContext()) ?: return@apply
                        flags = Intent.FLAG_GRANT_READ_URI_PERMISSION
                        startActivity(this)
                    }
                }
            }

            override fun onLongClick(position: Int, viewBinding: LayoutAttachmentBinding): Boolean {
                val note = data.note ?: return false
                if (note.isDeleted) return false
                showAttachmentActions(note, attachmentsAdapter.getItemAtPosition(position))
                return true
            }
        }

        attachmentsAdapter = AttachmentsAdapter(listener)
        // Configure the recycler view
        recyclerAttachments.apply {
            layoutManager = AttachmentsGridManager(requireContext())
            adapter = attachmentsAdapter
        }
    }

    private fun showAttachmentActions(note: Note, attachment: Attachment) {
        if (note.isDeleted) return
        BottomSheet.show(attachment.description, parentFragmentManager) {
            action(R.string.attachments_edit_description, R.drawable.ic_pencil) {
                EditAttachmentDialog.build(note.id, attachment.path).show(parentFragmentManager, null)
            }
            action(R.string.action_delete, R.drawable.ic_bin) {
                val editor = binding.editTextContent
                val marker = "[journal-media:${InlineMedia.id(attachment)}]"
                val text = editor.text.toString()
                if (marker in text) {
                    replaceBody(text.replace(marker, ""), bodyOffset().coerceAtLeast(0))
                }
                model.deleteAttachment(attachment)
            }
            action(R.string.action_share, R.drawable.ic_share) {
                shareAttachment(requireContext(), attachment)
            }
        }
    }

    private fun setMarkdownToolbarVisibility(note: Note? = data.note) = with(binding) {
        if (note == null) return@with

        containerBottomToolbar.isVisible = !isList && note.isMarkdownEnabled && model.inEditMode && contentHasFocus

        scrollView.updateLayoutParams<ConstraintLayout.LayoutParams> {
            val actionBarSize = requireContext().getDimensionAttribute(R.attr.actionBarSize) ?: 0
            bottomMargin = when {
                containerBottomToolbar.isVisible -> actionBarSize
                else -> 0
            }
        }
    }

    private fun setupEditTexts() = with(binding) {
        editTextTitle.apply {
            imeOptions = EditorInfo.IME_ACTION_NEXT
            setRawInputType(InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES)

            setOnEditorActionListener { _, actionId, _ ->
                when {
                    actionId == EditorInfo.IME_ACTION_NEXT && data.note?.isList == true -> {
                        jumpToNextTaskOrAdd(-1)
                        true
                    }

                    else -> false
                }
            }

            doOnTextChanged { text, _, _, _ ->
                // Only listen for meaningful changes
                if (data.note == null) {
                    return@doOnTextChanged
                }

                model.setNoteTitle(text.toString().trim())
            }
        }

        editTextContent.apply {
            enableUndoRedo(this@EditorFragment)
            setRawInputType(InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES)
            doOnTextChanged { text, _, _, _ ->
                // Only listen for meaningful changes, we do not care about empty text
                if (data.note == null) {
                    return@doOnTextChanged
                }

                model.setNoteContent(text.toString())
            }
            setOnFocusChangeListener { _, hasFocus ->
                contentHasFocus = hasFocus
                setMarkdownToolbarVisibility()
            }


            addTextChangedListener(object : TextWatcher {
                var changedText = ""
                private val listRegex = Regex("^((\\s*)([\\-+*] +)).*")
                private val checkRegex = Regex("^((\\s*)[-+*] *\\[([ xX])] +).*")
                private val numListRegex = Regex("((\\s*)([1-9][0-9]*)[.] +).*")
                private val indentedLine = Regex("((\\s+)).*")

                override fun beforeTextChanged(s: CharSequence?, start: Int, count: Int, after: Int) {}

                override fun onTextChanged(s: CharSequence?, start: Int, before: Int, count: Int) {
                    changedText = s?.substring(start, start + count).toString()
                }

                override fun afterTextChanged(s: Editable?) {
                    if (changedText.endsWith('\n')) {
                        val txt = text ?: return
                        val prevLine = txt.lines().getOrNull(currentLineIndex - 1) ?: return
                        when {
                            prevLine.matches(checkRegex) -> nextListLine(checkRegex, prevLine, txt, "- [ ] ")
                            prevLine.matches(listRegex) -> nextListLine(listRegex, prevLine, txt)
                            prevLine.matches(numListRegex) -> {
                                val nextNum = numListRegex.find(prevLine)?.groupValues?.get(3)?.toInt()?.inc() ?: 1
                                nextListLine(numListRegex, prevLine, txt, "$nextNum. ")
                            }

                            prevLine.matches(indentedLine) -> nextListLine(indentedLine, prevLine, txt)
                        }
                    }
                }

                private fun nextListLine(regex: Regex, line: String, text: Editable, suffix: String? = null) {
                    val groups = regex.find(line)?.groupValues
                    val matchedLine = groups?.getOrNull(1) ?: ""
                    if (matchedLine == line) {
                        text.delete(currentLineStartPos - line.length - 1, currentLineStartPos - 1)
                    } else {
                        val indent = groups?.getOrNull(2) ?: ""
                        text.insert(currentLineStartPos, "$indent${suffix ?: groups?.getOrNull(3) ?: ""}")
                    }
                }
            })

            setOnCanUndoRedoListener { canUndo, canRedo ->
                binding.bottomToolbar.menu?.run {
                    findItem(R.id.action_undo).isEnabled = canUndo
                    findItem(R.id.action_redo).isEnabled = canRedo
                }
            }
        }

        // Used to clear focus and hide the keyboard when touching outside of the edit texts
        linearLayout.setOnFocusChangeListener { _, hasFocus ->
            if (hasFocus) root.hideKeyboard()
        }
    }

    private fun setupMenuItems(note: Note, hasReminders: Boolean) = mainMenu?.run {
        findItem(R.id.action_restore_note)?.isVisible = note.isDeleted
        findItem(R.id.action_delete_permanently_note)?.isVisible = note.isDeleted
        findItem(R.id.action_delete_note)?.isVisible = !note.isDeleted
        findItem(R.id.action_view_tags)?.isVisible = !note.isDeleted
        findItem(R.id.action_change_color)?.isVisible = !note.isDeleted
        findItem(R.id.action_attach_file)?.isVisible = !note.isDeleted
        findItem(R.id.action_record_audio)?.isVisible = !note.isDeleted
        findItem(R.id.action_take_photo)?.isVisible = !note.isDeleted
        findItem(R.id.action_record_video)?.isVisible = !note.isDeleted
        findItem(R.id.action_add_location)?.isVisible = !note.isDeleted && !note.isList
        findItem(R.id.action_journal_dictation)?.isVisible = !note.isDeleted && !note.isList
        if (!note.isDeleted && !note.isList) bindDictationGesture()
        findItem(R.id.action_convert_note)?.apply {
            title =
                if (note.isList) getString(R.string.action_convert_to_note) else getString(R.string.action_convert_to_list)
            isVisible = !note.isDeleted
        }

        findItem(R.id.action_change_mode)?.apply {
            // if view/edit mode FAB isn't displayed (user pref) show it in the top menu
            if (!data.showFabChangeMode) {
                setIcon(if (model.inEditMode) R.drawable.ic_show else R.drawable.ic_pencil)

                isVisible = !note.isDeleted && !hasNoteEmptyContent(note)
            }
        }

        findItem(R.id.action_pin_note)?.apply {
            setIcon(if (note.isPinned) R.drawable.ic_pin_filled else R.drawable.ic_pin)
            setTitle(if (note.isPinned) R.string.action_unpin else R.string.action_pin)
            isVisible = !note.isDeleted
        }

        findItem(R.id.action_view_reminders)?.apply {
            setIcon(if (hasReminders) R.drawable.ic_bell_filled else R.drawable.ic_bell)
            isVisible = !note.isDeleted
        }

        findItem(R.id.action_archive_note)?.apply {
            title = if (note.isArchived) getString(R.string.action_unarchive) else getString(R.string.action_archive)
            isVisible = !note.isDeleted
        }

        findItem(R.id.action_enable_disable_markdown)?.apply {
            title =
                if (note.isMarkdownEnabled) getString(R.string.action_disable_markdown) else getString(R.string.action_enable_markdown)
            isVisible = !note.isDeleted
        }

        findItem(R.id.action_hide_note)?.apply {
            isChecked = note.isHidden
            isVisible = !note.isDeleted
        }

        findItem(R.id.action_do_not_sync)?.apply {
            isChecked = note.isLocalOnly
            isVisible = !note.isDeleted
        }

        findItem(R.id.action_screen_always_on)?.apply {
            isChecked = note.screenAlwaysOn
            isVisible = !note.isDeleted
        }

        findItem(R.id.action_uncheck_all_tasks)?.apply {
            isVisible = note.isList && !note.isDeleted
        }

        findItem(R.id.action_remove_all_checked_tasks)?.apply {
            isVisible = note.isList && !note.isDeleted
        }
    }

    private fun observeData() = with(binding) {
        model.data.collect(viewLifecycleOwner) { data ->
            if (data.note == null && data.isInitialized) {
                return@collect run { findNavController().navigateUp() }
            }

            if (!data.isInitialized || data.note == null) return@collect

            this@EditorFragment.data = data

            val isConverted = data.note.isList != isList
            val isMarkdownEnabled = data.note.isMarkdownEnabled
            val (dateFormat, timeFormat) = data.dateTimeFormats
            val screenAlwaysOn = data.note.screenAlwaysOn

            isList = data.note.isList
            isNoteDeleted = data.note.isDeleted

            if (isMarkdownEnabled) {
                enableMarkdownTextWatcher()
            } else {
                disableMarkdownTextWatcher()
            }

            setupScreenAlwaysOn(screenAlwaysOn)

            // Update Title and Content only the first the since they are EditTexts
            if (isFirstLoad) {
                requireContext().getSharedPreferences("journal", Context.MODE_PRIVATE).edit()
                    .putLong("activeNote", data.note.id).apply()

                if (!isList || data.defaultEditorMode == DefaultEditorMode.EDIT) {
                    model.inEditMode = true
                }

                // apply font size preference
                if (data.editorFontSize != -1) { // is customised
                    val fontSizeFloat = data.editorFontSize.toFloat()

                    textViewTitlePreview.textSize = fontSizeFloat

                    editTextTitle.textSize = fontSizeFloat
                    editTextContent.textSize = fontSizeFloat

                    if (isList) {
                        tasksAdapter.setFontSize(fontSizeFloat)
                    }
                }

                editTextTitle.withoutTextWatchers {
                    setText(data.note.title)
                }

                when {
                    isList -> tasksAdapter.submitList(data.note.taskList)
                    else -> {
                        viewLifecycleOwner.lifecycleScope.launchWhenResumed {
                            editTextContent.withOnlyTextWatcher<MarkwonEditorTextWatcher> {
                                setText(data.note.content)
                            }
                            val (selStart, selEnd) = model.selectedRange
                            if (selStart >= 0 && selEnd <= editTextContent.length()) {
                                editTextContent.setSelection(selStart, selEnd)
                            }
                            if (!isList) renderBodyPreview(data.note)
                        }
                    }
                }

                nextTaskId = data.note.taskList.maxOfOrNull { it.id }?.plus(1) ?: 0L
            }

            // We only want to update the task list when the user converts the note from text to list
            if (isConverted) {

                if (data.editorFontSize != -1) {
                    tasksAdapter.setFontSize(data.editorFontSize.toFloat())
                }

                tasksAdapter.tasks.clear()
                tasksAdapter.notifyDataSetChanged()
                tasksAdapter.submitList(data.note.taskList)
                editTextContent.withOnlyTextWatcher<MarkwonEditorTextWatcher> {
                    setText(data.note.content)
                }
            }
            recyclerTasks.isVisible = isList

            updateEditMode(note = data.note)

            // Must be called after updateEditMode since that method changes the visibility of the inputs
            if (isFirstLoad) requestFocusForFields()

            // Also set text of preview textviews
            textViewTitlePreview.text = data.note.title.ifEmpty { getString(R.string.indicator_untitled) }

            if (!model.inEditMode || (previewedNote?.content == data.note.content &&
                    previewedNote?.attachments != data.note.attachments)) renderBodyPreview(data.note)

            setupMenuItems(data.note, data.note.reminders.isNotEmpty())

            // Update notebook indicator
            notebookView.setCompoundDrawablesRelativeWithIntrinsicBounds(
                requireContext().getDrawableCompat(R.drawable.ic_notebook),
                null,
                requireContext().getDrawableCompat(if (data.notebook == null) R.drawable.ic_add else R.drawable.ic_swap),
                null
            )
            notebookView.text = data.notebook?.name ?: getString(R.string.notebooks_unassigned)

            // Update fragment background colour
            data.note.color.resId(requireContext())?.let { resId ->
                backgroundColor = resId
                root.setBackgroundColor(resId)
                containerBottomToolbar.setBackgroundColor(resId)
                toolbar.setBackgroundColor(resId)
            }

            // Update date
            val offset = ZoneId.systemDefault().rules.getOffset(Instant.now())
            val creationDate = LocalDateTime.ofEpochSecond(data.note.creationDate, 0, offset)
            val modifiedDate = LocalDateTime.ofEpochSecond(data.note.modifiedDate, 0, offset)

            formatter =
                DateTimeFormatter.ofPattern("${getString(dateFormat.patternResource)}, ${getString(timeFormat.patternResource)}")

            textViewDate.isVisible = data.showDates
            if (formatter != null && data.showDates) {
                textViewDate.text =
                    getString(
                        R.string.indicator_note_date,
                        creationDate.format(formatter),
                        modifiedDate.format(formatter)
                    )
            }

            // We want to start the transition only when everything is loaded
            binding.root.doOnPreDraw {
                startPostponedEnterTransition()
            }

            if (isNoteDeleted) {
                snackbar = Snackbar.make(binding.root, "", Snackbar.LENGTH_INDEFINITE)
                    .setText(getString(R.string.indicator_deleted_note_cannot_be_edited))
                    .setAction(getString(R.string.action_restore)) { _ ->
                        activityModel.restoreNotes(data.note)
                        activity?.onBackPressedDispatcher?.onBackPressed()
                    }
                snackbar?.show()
                snackbar?.addCallback(object : BaseTransientBottomBar.BaseCallback<Snackbar>() {
                    override fun onShown(transientBottomBar: Snackbar?) {
                        super.onShown(transientBottomBar)
                        scrollView.apply {
                            setPadding(paddingLeft, paddingTop, paddingRight, snackbar?.view?.height ?: paddingBottom)
                        }
                    }
                })
            }

            // Update attachments
            val embedded = InlineMedia.marker.findAll(data.note.content).map { it.groupValues[1] }.toSet()
            attachmentsAdapter.submitList(data.note.attachments.filterNot { InlineMedia.id(it) in embedded })

            // Update tags
            containerTags.removeAllViews()
            data.note.tags.forEach { tag ->
                containerTags.addView(
                    TextView(ContextThemeWrapper(requireContext(), R.style.TagChip)).apply {
                        text = "# ${tag.name}"
                    }
                )
            }

            isFirstLoad = false
        }
    }

    private fun showSavedPreview(note: Note) {
        renderBodyPreview(note)
        viewLifecycleOwner.lifecycleScope.launch {
            model.savedNote()?.takeIf { !model.inEditMode }?.let(::renderBodyPreview)
        }
    }

    private fun renderBodyPreview(note: Note) = with(binding) {
        val markers = InlineMedia.marker.findAll(note.content).toList()
        val editable = model.inEditMode && !note.isDeleted
        containerBodyPreview.isVisible = !isList && (!editable || markers.isNotEmpty())
        editTextContent.isVisible = !isList && editable && markers.isEmpty()
        val previous = previewedNote
        if (previewWasEditable == editable && previous != null && previous.content == note.content && previous.attachments == note.attachments &&
            previous.isMarkdownEnabled == note.isMarkdownEnabled) return@with
        previewedNote = note
        previewWasEditable = editable
        activeBodyField = null
        bodyFields.clear()
        inlinePlayer?.stopPlayback()
        inlinePlayer = null
        containerBodyPreview.removeAllViews()

        if (editable && markers.isEmpty()) return@with

        fun addText(content: String, section: Int) {
            if (editable) {
                val field = ExtendedEditText(requireContext()).apply {
                    textSize = data.editorFontSize.takeIf { it > 0 }?.toFloat() ?: 16f
                    inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_FLAG_MULTI_LINE or
                        InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
                    background = null
                    setPadding(0, 8.dp(context), 0, 8.dp(context))
                    minHeight = 42.dp(context)
                    setText(content)
                    enableUndoRedo(this@EditorFragment)
                    setOnFocusChangeListener { _, focused ->
                        if (focused) activeBodyField = this
                        contentHasFocus = focused
                        setMarkdownToolbarVisibility()
                    }
                    doOnTextChanged { value, _, _, _ ->
                        val canonical = editTextContent.text.toString()
                        val matches = InlineMedia.marker.findAll(canonical).toList()
                        val first = matches.getOrNull(section - 1)?.range?.last?.plus(1) ?: 0
                        val last = matches.getOrNull(section)?.range?.first ?: canonical.length
                        val sectionText = value.toString()
                        val leading = if (section > 0 && !sectionText.startsWith('\n')) "\n" else ""
                        val trailing = if (section < matches.size && !sectionText.endsWith('\n')) "\n" else ""
                        val updated = canonical.replaceRange(first, last, leading + sectionText + trailing)
                        editTextContent.withOnlyTextWatcher<MarkwonEditorTextWatcher> { setText(updated) }
                        previewedNote = previewedNote?.copy(content = updated)
                        model.setNoteContent(updated)
                    }
                }
                bodyFields.add(field)
                containerBodyPreview.addView(field, -1, -2)
                return
            }
            if (content.isBlank()) return
            val text = TextView(requireContext()).apply {
                textSize = data.editorFontSize.takeIf { it > 0 }?.toFloat() ?: 16f
                setTextIsSelectable(true)
                movementMethod = LinkMovementMethod.getInstance()
                setPadding(0, 8.dp(context), 0, 8.dp(context))
            }
            containerBodyPreview.addView(text)
            if (note.isMarkdownEnabled) {
                markwon.applyTo(text, content.trim()) {
                    tableReplacement = { Code(getString(R.string.message_cannot_preview_table)) }
                    maximumTableColumns = 15
                }
                text.movementMethod = LinkMovementMethod.getInstance()
            } else {
                text.text = content.trim()
                Linkify.addLinks(text, Linkify.WEB_URLS)
            }
        }

        val linked = note.attachments.associateBy(InlineMedia::id)
        var start = 0
        for ((index, marker) in markers.withIndex()) {
            addText(note.content.substring(start, marker.range.first), index)
            start = marker.range.last + 1
            val attachment = linked[marker.groupValues[1]] ?: continue
            val uri = attachment.uri(requireContext()) ?: continue
            if (attachment.type == Attachment.Type.IMAGE) {
                containerBodyPreview.addView(ImageView(requireContext()).apply {
                    adjustViewBounds = true
                    contentDescription = attachment.description
                    setOnLongClickListener { showAttachmentActions(note, attachment); true }
                    load(uri)
                }, -1, -2)
            } else if (attachment.type == Attachment.Type.VIDEO) {
                val context = requireContext()
                val frame = android.widget.FrameLayout(context)
                containerBodyPreview.addView(frame, -1, 220.dp(context))
                val poster = ImageView(context).apply {
                    scaleType = ImageView.ScaleType.FIT_CENTER
                    load(uri)
                }
                frame.addView(poster, -1, -1)
                val player = VideoView(context).apply {
                    visibility = View.GONE
                    val controls = MediaController(context)
                    setMediaController(controls)
                    setOnPreparedListener { controls.show(3000) }
                    setOnErrorListener { _, _, _ ->
                        sendMessage(getString(R.string.journal_video_playback_failed))
                        true
                    }
                }
                frame.addView(player, android.widget.FrameLayout.LayoutParams(-1, -1, android.view.Gravity.CENTER))
                val play = Button(context).apply {
                    setText(R.string.journal_play_video)
                    setOnClickListener {
                        inlinePlayer?.takeIf { it !== player }?.stopPlayback()
                        inlinePlayer = player
                        poster.isVisible = false
                        isVisible = false
                        player.isVisible = true
                        player.setVideoURI(uri)
                        player.start()
                    }
                }
                play.setOnLongClickListener { showAttachmentActions(note, attachment); true }
                frame.addView(play, android.widget.FrameLayout.LayoutParams(-2, -2, android.view.Gravity.CENTER))
            }
        }
        addText(note.content.substring(start), markers.size)
    }

    private fun setupListeners() = with(binding) {
        bottomToolbar.setOnMenuItemClickListener {
            val editTextContent = activeBodyField ?: binding.editTextContent
            val span = when (it.itemId) {
                R.id.action_insert_bold -> MarkdownSpan.BOLD
                R.id.action_insert_italics -> MarkdownSpan.ITALICS
                R.id.action_insert_strikethrough -> MarkdownSpan.STRIKETHROUGH
                R.id.action_insert_code -> MarkdownSpan.CODE
                R.id.action_insert_quote -> MarkdownSpan.QUOTE
                R.id.action_insert_heading -> MarkdownSpan.HEADING
                R.id.action_insert_highlight -> MarkdownSpan.HIGHLIGHT
                R.id.action_insert_link -> {
                    clearFragmentResult(MARKDOWN_DIALOG_RESULT)
                    InsertHyperlinkDialog
                        .build(editTextContent.selectedText ?: "")
                        .show(parentFragmentManager, null)
                    null
                }

                R.id.action_insert_image -> {
                    clearFragmentResult(MARKDOWN_DIALOG_RESULT)
                    InsertImageDialog
                        .build(editTextContent.selectedText ?: "")
                        .show(parentFragmentManager, null)
                    null
                }

                R.id.action_insert_table -> {
                    clearFragmentResult(MARKDOWN_DIALOG_RESULT)
                    InsertTableDialog().show(parentFragmentManager, null)
                    null
                }

                R.id.action_toggle_check_line -> {
                    editTextContent.toggleCheckmarkCurrentLine()
                    null
                }

                R.id.action_scroll_to_top -> {
                    scrollView.smoothScrollTo(0, 0)
                    editTextContent.setSelection(0)
                    null
                }

                R.id.action_scroll_to_bottom -> {
                    scrollView.smoothScrollTo(
                        0,
                        editTextContent.bottom + editTextContent.paddingBottom + editTextContent.marginBottom
                    )
                    editTextContent.setSelection(editTextContent.length())
                    null
                }

                R.id.action_undo -> {
                    editTextContent.undo()
                    null
                }

                R.id.action_redo -> {
                    editTextContent.redo()
                    null
                }

                else -> return@setOnMenuItemClickListener false
            }
            editTextContent.insertMarkdown(span ?: return@setOnMenuItemClickListener false)
            true
        }

        notebookView.setOnClickListener {
            data.note?.let { showMoveToNotebookDialog(it) }
        }

        actionAddTask.setOnClickListener {
            // Always add new tasks at the top (position 0)
            addTask(0)
        }
    }

    private fun setupMarkdown() {
        markwonTextWatcher = MarkwonEditorTextWatcher.withPreRender(
            markwonEditor, Executors.newCachedThreadPool(),
            binding.editTextContent
        )
    }

    private fun enableMarkdownTextWatcher() = with(binding) {
        if (markwonTextWatcher != null && !editTextContent.isMarkdownEnabled) {
            // TextWatcher is created and currently not attached to the EditText, we attach it
            editTextContent.addTextChangedListener(markwonTextWatcher)

            // Re-set text to notify the listener
            editTextContent.withOnlyTextWatcher<MarkwonEditorTextWatcher> {
                setText(text)
            }

            editTextContent.isMarkdownEnabled = true
            setMarkdownToolbarVisibility()
        }
    }

    private fun disableMarkdownTextWatcher() = with(binding) {
        if (markwonTextWatcher != null && editTextContent.isMarkdownEnabled) {
            // TextWatcher is created and currently attached to the EditText, we detach it
            editTextContent.removeTextChangedListener(markwonTextWatcher)
            val text = editTextContent.text.toString()

            editTextContent.text?.clearSpans()
            editTextContent.withoutTextWatchers {
                setText(text)
            }

            editTextContent.isMarkdownEnabled = false
            setMarkdownToolbarVisibility()
        }
    }

    private fun setupScreenAlwaysOn(enable: Boolean) {
        if (enable) {
            activity?.window?.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        } else {
            activity?.window?.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        }
    }

    override fun setupToolbar(): Unit = with(binding) {
        super.setupToolbar()
        val onBackPressedHandler = {
            if (findNavController().navigateUp()) {
                requireContext().getSharedPreferences("journal", Context.MODE_PRIVATE).edit()
                    .remove("activeNote").apply()
                // This is needed because "Notes" label briefly appears
                // during the shared element transition when returning.
                // Todo: Needs a better fix
                toolbar.setTitleTextColor(Color.TRANSPARENT)

                // This is needed because the view jumps around
                // during the shared element transition when returning.
                // Todo: Needs a better fix
                notebookView.isVisible = false
            }
        }

        toolbar.setNavigationOnClickListener { onBackPressedHandler() }
        activity?.onBackPressedDispatcher?.addCallback(viewLifecycleOwner) {
            if (!onBackPressHandled) {
                onBackPressedHandler()
                onBackPressHandled = true
            }
        }
    }

    private fun addTask(position: Int = 0) {
        tasksAdapter.tasks.add(position, NoteTask(nextTaskId, "", false))
        tasksAdapter.notifyItemInserted(position)

        if (position < tasksAdapter.tasks.size - 1) {
            tasksAdapter.notifyItemRangeChanged(position, tasksAdapter.tasks.size - position)
        }

        binding.recyclerTasks.doOnNextLayout {
            (binding.recyclerTasks.findViewHolderForAdapterPosition(position) as TaskViewHolder).requestFocus()
        }

        nextTaskId += 1
        model.updateTaskList(tasksAdapter.tasks)
    }

    private fun updateTask(position: Int, content: String? = null, isDone: Boolean? = null) {
        val tasks = tasksAdapter.tasks
        val oldTask = tasks[position]
        val newTask = tasks[position].copy(
            content = content ?: oldTask.content,
            isDone = isDone ?: oldTask.isDone
        )
        tasks[position] = newTask

        if (oldTask.isDone != newTask.isDone && model.moveCheckedItems) {
            binding.scrollView.findFocus()?.clearFocus()
            if (newTask.isDone) {
                // Move to very end
                tasks.removeAt(position)
                tasks.add(newTask)

                tasksAdapter.notifyItemMoved(position, tasks.indexOf(newTask))
                tasksAdapter.notifyItemRangeChanged(position, tasks.size - position)
            } else {
                // Move to after last open task or to very beginning if all tasks are done
                val newPosition = tasks.indexOfLast { it.id != newTask.id && !it.isDone } + 1

                // Only move upwards; don't move further down
                if (newPosition < position) {
                    tasks.removeAt(position)
                    tasks.add(newPosition, newTask)

                    tasksAdapter.notifyItemMoved(position, newPosition)
                    tasksAdapter.notifyItemRangeChanged(newPosition, position - newPosition + 1)
                }
            }
        }

        model.updateTaskList(tasksAdapter.tasks)
    }

    private fun showColorChangeDialog() {
        val selected = NoteColor.entries.indexOf(data.note?.color).coerceAtLeast(0)
        val dialog = BaseDialog.build(requireContext()) {
            setTitle(getString(R.string.action_change_color))
            setSingleChoiceItems(
                NoteColor.entries.map { it.localizedName }.toTypedArray(),
                selected
            ) { _, which ->
                model.setColor(NoteColor.entries[which])
            }
            setPositiveButton(getString(R.string.action_done)) { _, _ -> }
        }

        dialog.show()
    }

    private fun showRemindersDialog(note: Note) {
        BottomSheet.show(getString(R.string.reminders), parentFragmentManager) {
            data.note?.reminders?.forEach { reminder ->
                val offset = ZoneId.systemDefault().rules.getOffset(Instant.now())
                val reminderDate = LocalDateTime.ofEpochSecond(reminder.date, 0, offset)

                action(reminder.name + " (${reminderDate.format(formatter)})", R.drawable.ic_bell) {
                    checkSchedulePermission {
                        EditReminderDialog.build(note.id, reminder).show(parentFragmentManager, null)
                    }
                }
            }
            action(R.string.action_new_reminder, R.drawable.ic_add) {
                checkSchedulePermission {
                    EditReminderDialog.build(note.id, null).show(parentFragmentManager, null)
                }
            }
        }
    }

    private fun checkSchedulePermission(onPermissionGranted: () -> Unit) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val alarmManager = context?.getSystemService(AlarmManager::class.java)
            if (alarmManager?.canScheduleExactAlarms() != true) {
                val intent = Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM).apply {
                    data = Uri.fromParts("package", context?.packageName, null)
                }
                context?.startActivity(intent)
                return
            }
        }
        onPermissionGranted()
    }

    /** Gives the focus to the note body if it is empty */
    private fun requestFocusForFields(forceFocus: Boolean = false) = with(binding) {
        if (model.inEditMode && !isList && (data.note?.isEmpty() == true || forceFocus)) {
            (activeBodyField ?: bodyFields.lastOrNull() ?: editTextContent).requestFocusAndKeyboard()
        }
    }

    private fun updateEditMode(inEditMode: Boolean = model.inEditMode, note: Note? = data.note) = with(binding) {
        // If the note is empty the fragment should open in edit mode by default
        val noteHasEmptyContent = hasNoteEmptyContent(note)

        model.inEditMode = (inEditMode || noteHasEmptyContent) && !isNoteDeleted

        textViewTitlePreview.isVisible = !model.inEditMode
        editTextTitle.isVisible = model.inEditMode

        actionAddTask.isVisible = isList && model.inEditMode
        recyclerTasks.doOnPreDraw {
            for (pos in 0 until tasksAdapter.tasks.size) {
                (recyclerTasks.findViewHolderForAdapterPosition(pos) as? TaskViewHolder)?.isEnabled = model.inEditMode
            }
        }

        val hasEmbeddedMedia = InlineMedia.marker.containsMatchIn(editTextContent.text.toString())
        containerBodyPreview.isVisible = !isList && (!model.inEditMode || hasEmbeddedMedia)
        editTextContent.isVisible = model.inEditMode && !isList && !hasEmbeddedMedia

        val shouldDisplayFAB = data.showFabChangeMode && !isNoteDeleted && !noteHasEmptyContent
        when {
            fabChangeMode.isVisible == shouldDisplayFAB -> { /* FAB is already like it should be, no reason to animate */
            }

            fabChangeMode.isVisible && !shouldDisplayFAB -> fabChangeMode.hide()
            else -> fabChangeMode.show()
        }

        fabChangeMode.setImageResource(if (model.inEditMode) R.drawable.ic_show else R.drawable.ic_pencil)
        setMarkdownToolbarVisibility(note)
    }

    private fun hasNoteEmptyContent(note: Note? = data.note): Boolean {
        return note?.content?.isBlank() == true || (note?.isList == true && note.taskList.isEmpty())
    }

    private fun uncheckAllTasks() {
        binding.scrollView.findFocus()?.clearFocus()
        val updatedTasks = tasksAdapter.tasks.map { task ->
            task.copy(isDone = false)
        }
        tasksAdapter.submitList(updatedTasks)

        model.updateTaskList(updatedTasks)
    }

    private fun removeAllCheckedTasks() {
        binding.scrollView.findFocus()?.clearFocus()
        val updatedTasks = tasksAdapter.tasks.filter { task ->
            !task.isDone
        }
        tasksAdapter.submitList(updatedTasks)

        model.updateTaskList(updatedTasks)
    }

    private val NoteColor.localizedName
        get() = getString(
            when (this) {
                NoteColor.Default -> R.string.default_string
                NoteColor.Red -> R.string.preferences_color_scheme_red
                NoteColor.Orange -> R.string.preferences_color_scheme_orange
                NoteColor.Yellow -> R.string.preferences_color_scheme_yellow
                NoteColor.Green -> R.string.preferences_color_scheme_green
                NoteColor.Teal -> R.string.preferences_color_scheme_teal
                NoteColor.Cyan -> R.string.preferences_color_scheme_cyan
                NoteColor.Blue -> R.string.preferences_color_scheme_blue
                NoteColor.Purple -> R.string.preferences_color_scheme_purple
                NoteColor.Pink -> R.string.preferences_color_scheme_pink
                NoteColor.Brown -> R.string.preferences_color_scheme_brown
                NoteColor.Gray -> R.string.preferences_color_scheme_gray
            }
        )

    companion object {
        const val MARKDOWN_DIALOG_RESULT = "MARKDOWN_DIALOG_RESULT"
    }
}
