package io.github.yyyzsj.ygodiy;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.ImageDecoder;
import android.net.Uri;
import android.util.AtomicFile;
import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;
import java.io.*;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.Locale;
import java.util.zip.*;

/** 草稿是原子写入的清单，图片按内容共用。工程交换沿用桌面 .ydiy 的 ZIP 格式。 */
final class CardFiles {
    private static final int MIB = 1024 * 1024;
    private static final int MAX_ART = 32 * MIB, MAX_JSON = 12 * MIB, MAX_PACK = 256 * MIB;
    private static final int MAX_CARDS = 800, MAX_SIDE = 2200;
    private static final String FORMAT = "ygodiy-transfer/1";
    private final Context context;
    private final File artDir;
    private final AtomicFile draft;

    CardFiles(Context context) {
        this.context = context;
        artDir = new File(context.getFilesDir(), "art");
        draft = new AtomicFile(new File(context.getFilesDir(), "draft.json"));
    }

    synchronized String readDraft() throws IOException {
        try (InputStream stream = draft.openRead()) {
            return new String(bytes(stream, MAX_JSON), StandardCharsets.UTF_8);
        } catch (FileNotFoundException e) { return ""; }
    }

    synchronized void saveDraft(String json) throws IOException {
        byte[] data = json.getBytes(StandardCharsets.UTF_8);
        if (data.length > MAX_JSON) throw new IOException("草稿过大，请先导出卡包备份。");
        FileOutputStream stream = draft.startWrite();
        try { stream.write(data); draft.finishWrite(stream); }
        catch (IOException e) { draft.failWrite(stream); throw e; }
    }

    private static long copy(InputStream in, OutputStream out, long limit) throws IOException {
        if (in == null) throw new IOException("无法打开所选文件。");
        long size = 0;
        byte[] buffer = new byte[32768];
        int n;
        while ((n = in.read(buffer)) != -1) {
            size += n;
            if (size > limit) throw new IOException("文件超出可导入的大小。");
            out.write(buffer, 0, n);
        }
        return size;
    }

    private static byte[] bytes(InputStream in, int limit) throws IOException {
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        copy(in, out, limit);
        return out.toByteArray();
    }

    InputStream art(String id) throws IOException {
        if (id.equals("builtin-demo")) return context.getAssets().open("frames/demo.webp");
        if (!id.matches("[0-9a-f]{64}")) throw new IOException("卡图编号无效。");
        return new FileInputStream(new File(artDir, id));
    }

    String importImage(Uri uri) throws Exception {
        try (InputStream in = context.getContentResolver().openInputStream(uri)) {
            return storeImage(bytes(in, MAX_ART));
        }
    }

    private String storeImage(byte[] input) throws Exception {
        Bitmap bitmap = ImageDecoder.decodeBitmap(ImageDecoder.createSource(ByteBuffer.wrap(input)), (decoder, info, source) -> {
            int w = info.getSize().getWidth(), h = info.getSize().getHeight();
            if (Math.max(w, h) > MAX_SIDE) {
                double ratio = (double) MAX_SIDE / Math.max(w, h);
                decoder.setTargetSize(Math.max(1, (int)(w * ratio)), Math.max(1, (int)(h * ratio)));
            }
            decoder.setAllocator(ImageDecoder.ALLOCATOR_SOFTWARE);
        });
        ByteArrayOutputStream out = new ByteArrayOutputStream();
        try {
            if (!bitmap.compress(Bitmap.CompressFormat.PNG, 100, out)) throw new IOException("卡图转换失败。");
        } finally { bitmap.recycle(); }
        byte[] data = out.toByteArray();
        StringBuilder id = new StringBuilder();
        for (byte value : MessageDigest.getInstance("SHA-256").digest(data))
            id.append(String.format(Locale.ROOT, "%02x", value & 255));
        if (!artDir.isDirectory() && !artDir.mkdirs()) throw new IOException("无法建立卡图目录。");
        File target = new File(artDir, id.toString());
        if (!target.isFile()) {
            AtomicFile image = new AtomicFile(target);
            FileOutputStream stream = image.startWrite();
            try { stream.write(data); image.finishWrite(stream); }
            catch (IOException e) { image.failWrite(stream); throw e; }
        }
        return id.toString();
    }

    private static JSONArray cards(JSONObject manifest) throws Exception {
        String kind = manifest.optString("kind");
        if (!FORMAT.equals(manifest.optString("format")) || !(kind.equals("card") || kind.equals("pack")))
            throw new IOException("请选择 YGODIY 导出的 .ydiy 工程。");
        JSONArray cards = manifest.getJSONArray("cards");
        if (cards.length() == 0 || cards.length() > MAX_CARDS)
            throw new IOException("单个工程需要包含 1 至 " + MAX_CARDS + " 张卡。");
        return cards;
    }

    JSONObject importPack(Uri uri) throws Exception {
        File temp = File.createTempFile("import-", ".zip", context.getCacheDir());
        try {
            try (InputStream in = context.getContentResolver().openInputStream(uri);
                 OutputStream out = new FileOutputStream(temp)) { copy(in, out, MAX_PACK); }
            try (ZipFile zip = new ZipFile(temp)) {
                ZipEntry file = zip.getEntry("manifest.json");
                if (file == null) throw new IOException("工程缺少 manifest.json。");
                JSONObject manifest;
                try (InputStream in = zip.getInputStream(file)) {
                    manifest = new JSONObject(new String(bytes(in, MAX_JSON), StandardCharsets.UTF_8));
                }
                JSONArray cards = cards(manifest);
                long remaining = MAX_PACK;
                for (int i = 0; i < cards.length(); i++) {
                    JSONObject card = cards.getJSONObject(i);
                    String path = card.optString("image");
                    card.remove("image");
                    if (path.isEmpty()) continue;
                    ZipEntry entry = zip.getEntry(path);
                    if (entry == null || entry.isDirectory()) throw new IOException("工程缺少卡图。");
                    try (InputStream in = zip.getInputStream(entry)) {
                        byte[] art = bytes(in, (int)Math.min(remaining, MAX_ART));
                        remaining -= art.length;
                        card.put("image", storeImage(art));
                    }
                }
                return manifest;
            }
        } finally { temp.delete(); }
    }

    void writePack(File output, String json) throws Exception {
        JSONObject manifest = new JSONObject(json);
        JSONArray cards = cards(manifest);
        long remaining = MAX_PACK;
        try (ZipOutputStream zip = new ZipOutputStream(new BufferedOutputStream(new FileOutputStream(output)))) {
            for (int i = 0; i < cards.length(); i++) {
                JSONObject card = cards.getJSONObject(i);
                String id = card.optString("image");
                if (id.isEmpty()) continue;
                String path = "images/" + i + ".img";
                zip.putNextEntry(new ZipEntry(path));
                try (InputStream in = art(id)) { remaining -= copy(in, zip, Math.min(remaining, MAX_ART)); }
                zip.closeEntry();
                card.put("image", path);
            }
            zip.putNextEntry(new ZipEntry("manifest.json"));
            zip.write(manifest.toString().getBytes(StandardCharsets.UTF_8));
            zip.closeEntry();
        }
    }

    void finishExport(File snapshot, Uri uri) throws IOException {
        try (InputStream in = new FileInputStream(snapshot);
             OutputStream out = context.getContentResolver().openOutputStream(uri, "wt")) {
            if (out == null) throw new IOException("无法写入所选位置。");
            copy(in, out, MAX_PACK + MAX_JSON);
        }
    }
}
