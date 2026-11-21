package io.github.yyyzsj.ygodiy;

import java.io.*;
import java.util.zip.CRC32;

/** Canvas 导出没有成品尺寸。写入 PNG 的物理分辨率，使裁完的卡高为 86 毫米。 */
final class PrintPng {
    private static final int PHYS = 0x70485973, IHDR = 0x49484452;
    private static final int PIXELS_PER_METRE = Math.round(2370f / 0.086f);

    static void write(OutputStream output, byte[] png) throws IOException {
        DataInputStream input = new DataInputStream(new ByteArrayInputStream(png));
        DataOutputStream out = new DataOutputStream(output);
        out.writeLong(input.readLong());
        while (input.available() >= 12) {
            int length = input.readInt(), type = input.readInt();
            if (length < 0 || length > input.available() - 4) throw new IOException("PNG 图片不完整。");
            byte[] data = new byte[length];
            input.readFully(data);
            int checksum = input.readInt();
            if (type == PHYS) continue;
            out.writeInt(length); out.writeInt(type); out.write(data); out.writeInt(checksum);
            if (type != IHDR) continue;
            ByteArrayOutputStream payload = new ByteArrayOutputStream(13);
            DataOutputStream p = new DataOutputStream(payload);
            p.writeInt(PHYS); p.writeInt(PIXELS_PER_METRE); p.writeInt(PIXELS_PER_METRE); p.writeByte(1);
            byte[] bytes = payload.toByteArray();
            CRC32 crc = new CRC32(); crc.update(bytes);
            out.writeInt(9); out.write(bytes); out.writeInt((int)crc.getValue());
        }
    }
}
