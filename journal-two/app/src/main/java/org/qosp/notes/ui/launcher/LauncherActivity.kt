package org.qosp.notes.ui.launcher

import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
import org.qosp.notes.ui.MainActivity

class LauncherActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        startActivity(Intent(this, MainActivity::class.java).setAction(Intent.ACTION_MAIN))
        finish()
    }
}
