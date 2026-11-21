package io.github.yyyzsj.ygodiy;

import android.app.Activity;
import android.content.Intent;
import android.content.ClipData;
import android.content.ClipboardManager;
import android.icu.text.Transliterator;
import org.json.JSONArray;
import android.content.pm.ApplicationInfo;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.util.Base64;
import android.view.View;
import android.webkit.*;
import android.widget.FrameLayout;
import org.json.JSONObject;
import java.io.*;
import java.util.ArrayDeque;
import java.util.concurrent.*;

public final class EditorActivity extends Activity {
    private static final int PICK_IMAGE = 20, PICK_PACK = 21, SAVE_FILE = 22;
    private static final String SNAPSHOT = "document-export.tmp";
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final ArrayDeque<String> messages = new ArrayDeque<>();
    private WebView page;
    private CardFiles files;
    private boolean ready, busy;
    private String targetCard = "";

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        files = new CardFiles(this);
        if (state != null) {
            busy = state.getBoolean("busy");
            targetCard = state.getString("card", "");
        }
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY);
        getWindow().setNavigationBarColor(Color.LTGRAY);
        FrameLayout area = new FrameLayout(this);
        area.setBackgroundColor(Color.LTGRAY);
        area.setOnApplyWindowInsetsListener((v, insets) -> {
            v.setPadding(insets.getSystemWindowInsetLeft(), insets.getSystemWindowInsetTop(),
                    insets.getSystemWindowInsetRight(), insets.getSystemWindowInsetBottom());
            return insets.consumeSystemWindowInsets();
        });
        page = new WebView(this);
        area.addView(page);
        setContentView(area);
        WebSettings settings = page.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setUseWideViewPort(true);
        settings.setSupportZoom(true);
        settings.setBuiltInZoomControls(true);
        settings.setDisplayZoomControls(false);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        WebView.setWebContentsDebuggingEnabled((getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0);
        page.setWebViewClient(new LocalPage(getAssets(), files));
        page.addJavascriptInterface(new Documents(), "Documents");
        page.loadUrl(LocalPage.HOME + "index.html");
    }

    private class Documents {
        @JavascriptInterface public void initialized() {
            runOnUiThread(() -> { ready = true; while (!messages.isEmpty()) deliver(messages.remove()); });
        }
        @JavascriptInterface public String draft() {
            try { return files.readDraft(); }
            catch (Exception e) { return "!读取草稿失败"; }
        }
        @JavascriptInterface public boolean save(String draft) {
            try { files.saveDraft(draft); return true; }
            catch (Exception e) { return false; }
        }
        @JavascriptInterface public void pickImage(String id) { runOnUiThread(() -> open(PICK_IMAGE, id)); }
        @JavascriptInterface public void importPack() { runOnUiThread(() -> open(PICK_PACK, "")); }
        @JavascriptInterface public void exportPack(String name, String manifest) {
            runOnUiThread(() -> prepare(name, "application/octet-stream", f -> files.writePack(f, manifest)));
        }
        @JavascriptInterface public void exportImage(String name, String png) {
            runOnUiThread(() -> prepare(name, "image/png", f -> {
                try (OutputStream out = new FileOutputStream(f)) { PrintPng.write(out, Base64.decode(png, Base64.DEFAULT)); }
            }));
        }
        @JavascriptInterface public String chinese(String text, boolean traditional) {
            return Transliterator.getInstance(traditional ? "Simplified-Traditional" : "Traditional-Simplified").transliterate(text);
        }
        @JavascriptInterface public void copyText(String text) {
            runOnUiThread(() -> getSystemService(ClipboardManager.class).setPrimaryClip(ClipData.newPlainText("卡片文字", text)));
        }
        @JavascriptInterface public void authorLink(int index) {
            io.execute(() -> {
                try (InputStream in = getAssets().open("art.json"); java.util.Scanner scanner = new java.util.Scanner(in, "UTF-8")) {
                    String json = scanner.useDelimiter("\\A").next();
                    JSONArray links = new JSONObject(json).getJSONArray("support");
                    Uri link = Uri.parse(links.getJSONArray(index).getString(1));
                    if ("https".equals(link.getScheme())) runOnUiThread(() -> {
                        try { startActivity(new Intent(Intent.ACTION_VIEW, link)); } catch (RuntimeException e) { failed(e); }
                    });
                } catch (Exception e) { failed(e); }
            });
        }
        @JavascriptInterface public void exit() { runOnUiThread(() -> finish()); }
    }

    private interface Writer { void write(File file) throws Exception; }
    private File snapshot() { return new File(getCacheDir(), SNAPSHOT); }

    private void open(int kind, String id) {
        if (busy) return;
        busy = true;
        targetCard = id;
        Intent intent = new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                .setType(kind == PICK_IMAGE ? "image/*" : "*/*");
        launch(intent, kind);
    }

    private void prepare(String name, String mime, Writer writer) {
        if (busy) return;
        busy = true;
        io.execute(() -> {
            try {
                writer.write(snapshot());
                Intent intent = new Intent(Intent.ACTION_CREATE_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE)
                        .setType(mime).putExtra(Intent.EXTRA_TITLE, name);
                runOnUiThread(() -> launch(intent, SAVE_FILE));
            } catch (Exception e) { failed(e); }
        });
    }

    private void launch(Intent intent, int kind) {
        try { startActivityForResult(intent, kind); }
        catch (RuntimeException e) { failed(e); }
    }

    @Override protected void onActivityResult(int kind, int result, Intent data) {
        super.onActivityResult(kind, result, data);
        if (result != RESULT_OK || data == null || data.getData() == null) {
            if (kind == SAVE_FILE) snapshot().delete();
            busy = false;
            return;
        }
        Uri uri = data.getData();
        final String card = targetCard;
        io.execute(() -> {
            try {
                JSONObject event = new JSONObject();
                if (kind == PICK_IMAGE) {
                    event.put("type", "art").put("card", card).put("id", files.importImage(uri));
                } else if (kind == PICK_PACK) {
                    event.put("type", "import").put("manifest", files.importPack(uri));
                } else {
                    files.finishExport(snapshot(), uri);
                    event.put("type", "message").put("text", "已保存到所选位置");
                }
                runOnUiThread(() -> { busy = false; send(event.toString()); });
            } catch (Exception e) { failed(e); }
            finally { if (kind == SAVE_FILE) snapshot().delete(); }
        });
    }

    private void failed(Exception error) {
        String message = error.getMessage();
        String event = "{\"type\":\"message\",\"text\":" + JSONObject.quote("文件操作失败。" +
                (message == null ? "请重新选择文件。" : message)) + "}";
        runOnUiThread(() -> { busy = false; send(event); });
    }

    private void send(String event) { if (ready) deliver(event); else messages.add(event); }
    private void deliver(String event) {
        page.evaluateJavascript("window.receiveDocument(JSON.parse(" + JSONObject.quote(event) + "))", null);
    }

    @Override protected void onSaveInstanceState(Bundle state) {
        super.onSaveInstanceState(state);
        state.putBoolean("busy", busy);
        state.putString("card", targetCard);
    }

    @Override public void onBackPressed() {
        if (ready) page.evaluateJavascript("window.deviceBack()", null);
        else super.onBackPressed();
    }

    @Override protected void onDestroy() {
        ready = false;
        io.shutdown();
        page.destroy();
        super.onDestroy();
    }
}
