package com.localapi;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.security.KeyFactory;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.spec.PKCS8EncodedKeySpec;
import java.security.spec.X509EncodedKeySpec;
import javax.crypto.Cipher;

/**
 * RSA password cipher for the client's login contract.
 *
 * The 1.24.4 client encrypts every modern login/password payload with
 * RSA/ECB/PKCS1Padding before it leaves the app (com.sandbox.login.e.f
 * "RSAUtils", 117-byte chunks, Base64 NO_WRAP):
 *
 *   POST /user/api/v2/app/login            LoginRegisterAccountForm.password
 *   POST /user/api/v2/app/set-password     SetPasswordForm.password/confirmPassword
 *   POST /user/api/v2/user/password/modify ChangePasswordForm.old/newPassword
 *   POST /user/api/v1/user/password/check  @Query("password")
 *
 * The ORIGINAL production keypair is unrecoverable (the private half lived
 * on the real backend), so the local world mints its own fixed pair and
 * scripts/patch_rsa_key.py swaps the client's hardcoded public-key constant
 * for ours at APK build time. Server-side verification is then REAL RSA
 * decryption, not a canned response.
 *
 * Decryption failures fall back to the raw value — the same lenient
 * contract the client itself uses (LoginHelper.b returns the plaintext when
 * its cipher throws), and what keeps v1 plaintext flows (register, legacy
 * login, host-rig fcalls) working unchanged.
 *
 * NOTE: this "private key" protects nothing in a purely local, single-user
 * world — it is committed on purpose so builds and host tests stay
 * deterministic. It is NOT a repository credential.
 *
 * Host-rig note: uses a self-contained Base64 codec (no android.util.Base64)
 * so the same source runs on the JVM rig and on the device dex.
 */
public final class RsaCipher {
    /** X509/SPKI public key — scripts/patch_rsa_key.py embeds the same constant in the client. */
    public static final String PUBLIC_KEY_B64 =
        "MIGfMA0GCSqGSIb3DQEBAQUAA4GNADCBiQKBgQCp466bkyckAkuVRRPYusDNyW3urjleyz1ps//rKXI2jPzFAMZ6aI/PbMmFdxv3alnnSeO20vjmge2CwRAIFaJbp6h/OQvfONThKyfE/Y2StpuBdYTDOcOiVUQuE0YI+ROCHAKleLoJDFE1H70BByEq07Ha8slWiHxfJUMAi36wwwIDAQAB";

    /** PKCS8 private key — local-only, see class note. */
    private static final String PRIVATE_KEY_B64 =
        "MIICdwIBADANBgkqhkiG9w0BAQEFAASCAmEwggJdAgEAAoGBAKnjrpuTJyQCS5VFE9i6wM3Jbe6uOV7LPWmz/+spcjaM/MUAxnpoj89syYV3G/dqWedJ47bS+OaB7YLBEAgVolunqH85C9841OErJ8T9jZK2m4F1hMM5w6JVRC4TRgj5E4IcAqV4ugkMUTUfvQEHISrTsdryyVaIfF8lQwCLfrDDAgMBAAECgYA/ISUEGKVlwxiVCks6sQLuNViNZd5ZtEpI2iNSHl+bl75h8kzOtcYivPkRiFYzFSj9Qj7E9BabiVJZ0SYE6w0eSOwCjLZyOUe3Op421pOpLbgKK32tx5CMmbDuwGIlgtSsDRaBeAvJL0TNshaHriVz4PPQX6dHIUnVI6FT49EHAQJBANFAstrgFz0+xM8480YFf8MbDetx9Tw/cnlNV5Zn6NywMuM7OFvCOx1KIrZ8FRFrINzFePKB3/Bn0gHy5wQzI4ECQQDP18SKDxLMxt7vBfukJF6qXfvFHFjEkbF1tTeKzsdpEkinfyEFaGWHBYGJAhVGjCCKSNfo7M9B3F7T1j0Rd2ZDAkEAtXIgpOJDxHu1NOrxJ/qEuq2u+EYsnD14Ce8iz+zyYsr2lUs4p3hYwiES0KHvstbt/AHPypkLke60j7QM1ftyAQJAWENB5HsoOawOiiTZS0hipyjIPVmfXMKeQOVXE+xiBH3OOssjA7/ktaUh8EPhMxdYzkDG59SA43ApGP626k7xLwJBAMTSTHa/9vIVNlS7XlTAgUXX6X7mSoOBsId/1CpuR4n9BwFA7QlWv/7TRqbsYCIBFpvVpo+WdL0iLh41SM5u73c=";

    private static final int RSA_BYTES = 128;   // 1024-bit modulus
    private static final int CHUNK_MAX = 117;   // 128 - 11 (PKCS1 overhead)

    private RsaCipher() { }

    /** RSA-encrypt exactly like the client (chunked, Base64 NO_WRAP). Host-rig/test helper. */
    public static String encrypt(String plaintext) {
        try {
            Cipher cipher = Cipher.getInstance("RSA/ECB/PKCS1Padding");
            cipher.init(Cipher.ENCRYPT_MODE, publicKey());
            ByteArrayInputStream in =
                    new ByteArrayInputStream(plaintext.getBytes(StandardCharsets.UTF_8));
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            byte[] chunk = new byte[CHUNK_MAX];
            for (int n; (n = in.read(chunk)) != -1; ) {
                cipher.update(n == CHUNK_MAX ? chunk : java.util.Arrays.copyOf(chunk, n));
            }
            return b64Encode(out.toByteArray());
        } catch (Exception e) {
            return plaintext;
        }
    }

    /**
     * Decrypt a client password field. Returns the input unchanged when it
     * is not a valid RSA payload (Base64 decoding to whole 128-byte blocks),
     * so plaintext v1 flows pass through untouched.
     */
    public static String decryptIfEncrypted(String value) {
        if (value == null || value.length() < RSA_BYTES) return value;
        byte[] blob = b64Decode(value);
        if (blob == null || blob.length == 0 || blob.length % RSA_BYTES != 0) return value;
        try {
            Cipher cipher = Cipher.getInstance("RSA/ECB/PKCS1Padding");
            cipher.init(Cipher.DECRYPT_MODE, privateKey());
            ByteArrayOutputStream out = new ByteArrayOutputStream();
            for (int off = 0; off < blob.length; off += RSA_BYTES) {
                out.write(cipher.doFinal(blob, off, RSA_BYTES));
            }
            return new String(out.toByteArray(), StandardCharsets.UTF_8);
        } catch (Exception e) {
            return value;
        }
    }

    private static PublicKey publicKey() throws Exception {
        return KeyFactory.getInstance("RSA")
                .generatePublic(new X509EncodedKeySpec(b64Decode(PUBLIC_KEY_B64)));
    }

    private static PrivateKey privateKey() throws Exception {
        return KeyFactory.getInstance("RSA")
                .generatePrivate(new PKCS8EncodedKeySpec(b64Decode(PRIVATE_KEY_B64)));
    }

    // ---- self-contained Base64 (RFC 4648, NO_WRAP output, whitespace-tolerant input) ----

    private static final char[] B64 = ("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
            + "0123456789+/").toCharArray();

    private static String b64Encode(byte[] data) {
        StringBuilder sb = new StringBuilder(((data.length + 2) / 3) * 4);
        for (int i = 0; i < data.length; i += 3) {
            int b0 = data[i] & 0xFF;
            int b1 = (i + 1 < data.length) ? data[i + 1] & 0xFF : 0;
            int b2 = (i + 2 < data.length) ? data[i + 2] & 0xFF : 0;
            sb.append(B64[b0 >> 2]);
            sb.append(B64[((b0 & 0x3) << 4) | (b1 >> 4)]);
            sb.append((i + 1 < data.length) ? B64[((b1 & 0xF) << 2) | (b2 >> 6)] : '=');
            sb.append((i + 2 < data.length) ? B64[b2 & 0x3F] : '=');
        }
        return sb.toString();
    }

    private static byte[] b64Decode(String s) {
        if (s == null) return null;
        int[] rev = new int[128];
        java.util.Arrays.fill(rev, -1);
        for (int i = 0; i < B64.length; i++) rev[B64[i]] = i;
        ByteArrayOutputStream out = new ByteArrayOutputStream(s.length() * 3 / 4);
        int acc = 0, bits = 0;
        for (int i = 0; i < s.length(); i++) {
            char c = s.charAt(i);
            if (c == '=' || c == '\n' || c == '\r' || Character.isWhitespace(c)) continue;
            int v = (c < 128) ? rev[c] : -1;
            if (v < 0) return null;             // not Base64 -> caller treats as plaintext
            acc = (acc << 6) | v;
            bits += 6;
            if (bits >= 8) {
                bits -= 8;
                out.write((acc >> bits) & 0xFF);
            }
        }
        return out.toByteArray();
    }
}
