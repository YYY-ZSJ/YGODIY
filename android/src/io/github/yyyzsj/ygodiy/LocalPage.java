package io.github.yyyzsj.ygodiy;

import android.content.res.AssetManager;
import android.net.Uri;
import android.webkit.*;
import java.io.*;
import java.util.*;

final class LocalPage extends WebViewClient {
    static final String HOME = "https://appassets.androidplatform.net/";
    private final AssetManager assets;
    private final CardFiles files;
    LocalPage(AssetManager assets, CardFiles files) { this.assets = assets; this.files = files; }

    @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) { return true; }

    @Override public WebResourceResponse shouldInterceptRequest(WebView view, WebResourceRequest request) {
        Uri uri = request.getUrl();
        try {
            if (!"https".equals(uri.getScheme()) || !"appassets.androidplatform.net".equals(uri.getAuthority())
                    || !"GET".equals(request.getMethod())) throw new IOException();
            String path = uri.getPath().substring(1);
            if (path.contains("..") || path.contains("\\") || path.isEmpty()) throw new IOException();
            if (path.startsWith("art/")) return new WebResourceResponse("image/png", null, files.art(path.substring(4)));
            String ext = path.substring(path.lastIndexOf('.') + 1);
            String mime;
            switch (ext) {
                case "js": mime = "application/javascript"; break;
                case "css": mime = "text/css"; break;
                case "html": mime = "text/html"; break;
                case "svg": mime = "image/svg+xml"; break;
                case "json": mime = "application/json"; break;
                case "wasm": mime = "application/wasm"; break;
                case "png": mime = "image/png"; break;
                case "webp": mime = "image/webp"; break;
                case "py": mime = "text/plain"; break;
                default: mime = "application/octet-stream";
            }
            return new WebResourceResponse(mime, null, assets.open(path));
        } catch (Exception ignored) {
            return new WebResourceResponse("text/plain", "utf-8", 404, "Not Found",
                    Collections.emptyMap(), new ByteArrayInputStream(new byte[0]));
        }
    }
}
