# 修复 bridge_host.mjs 中的 NUL 字节：JS 字符串字面量里的真实 NUL → 文本转义 \0
b = open("bridge_host.mjs", "rb").read()
count = b.count(b"\x00")
print("NUL before:", count)
b = b.replace(b"\x00", b"\\0")  # 反斜杠+0 两字符（JS 八进制转义，与 emitConvFrame 同款）
open("bridge_host.mjs", "wb").write(b)
b2 = open("bridge_host.mjs", "rb").read()
print("NUL after:", b2.count(b"\x00"))
