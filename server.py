import os
import re
import requests
from datetime import datetime, timedelta, timezone
from fastapi import FastAPI, Request
from groq import Groq

app = FastAPI(title="AI CSKH & Chốt Lịch Webhook")

# 1. LẤY BIẾN MÔI TRƯỜNG TỪ RENDER
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
APPS_SCRIPT_URL = os.environ.get("APPS_SCRIPT_URL", "")

client = Groq(api_key=GROQ_API_KEY)

# Bộ nhớ tạm lưu lịch sử trò chuyện theo từng khách hàng (sender_id)
lich_su_hoi_thoai = {}

# 2. GỬI DỮ LIỆU KHÁCH ĐẶT LỊCH SANG GOOGLE SHEETS QUA APPS SCRIPT
def luu_len_google_sheet(ten_khach: str, sdt: str, dich_vu: str, thoi_gian: str, sender_id: str):
    if not APPS_SCRIPT_URL:
        return
    try:
        gio_vn = datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d %H:%M")
        requests.post(
            APPS_SCRIPT_URL,
            json={
                "thoi_gian_nhan": gio_vn,
                "ten_khach": ten_khach.strip(),
                "sdt": sdt.strip(),
                "dich_vu": dich_vu.strip(),
                "lich_hen": thoi_gian.strip(),
                "sender_id": str(sender_id),
            },
            timeout=8,
        )
    except Exception as e:
        print(f"Lỗi gửi sang Apps Script: {e}")

# 3. CHỌN MODEL GROQ THÔNG MINH & DỰ PHÒNG
def lay_danh_sach_model():
    tat_ca = [m.id for m in client.models.list().data]
    loai_bo = ["whisper", "guard", "tts", "orpheus", "allam", "distil"]
    hop_le = [m for m in tat_ca if not any(tk in m.lower() for tk in loai_bo)]
    uu_tien = [
        "gpt-oss-120b",
        "llama-4-maverick",
        "llama-3.3-70b",
        "kimi-k2",
        "qwen3-32b",
        "llama-4-scout",
        "llama-3.1-8b",
    ]
    ket_qua = []
    for u in uu_tien:
        for m in hop_le:
            if u in m.lower() and m not in ket_qua:
                ket_qua.append(m)
    for m in hop_le:
        if m not in ket_qua:
            ket_qua.append(m)
    return ket_qua

# 4. ĐỌC DỮ LIỆU TIỆM
if os.path.exists("du_lieu_tiem.txt"):
    with open("du_lieu_tiem.txt", "r", encoding="utf-8") as f:
        noi_dung_tiem = f.read()
else:
    noi_dung_tiem = "Cơ sở chăm sóc khách hàng."

SYSTEM_PROMPT = f"""
Bạn là chuyên viên tư vấn chăm sóc khách hàng chuyên nghiệp của cơ sở dưới đây.

DỮ LIỆU CƠ SỞ & BẢNG GIÁ DỊCH VỤ:
{noi_dung_tiem}

NGUYÊN TẮC TƯ VẤN:
1. Viết tiếng Việt chuẩn xác, tự nhiên, lịch sự, ngắn gọn (2-4 câu mỗi lượt nhắn để phù hợp giao diện Messenger/Zalo). Xưng "em", gọi khách là "anh/chị".
2. Chỉ tư vấn đúng dịch vụ/sản phẩm, mức giá, ưu đãi và giờ hoạt động có trong DỮ LIỆU CƠ SỞ. Không tự bịa thêm giá ngoài danh sách.
3. Quy trình chốt đơn / đặt lịch cần đủ 4 thông tin: 
   (1) Tên khách
   (2) Số điện thoại
   (3) Dịch vụ / Gói sản phẩm khách chọn
   (4) Thời gian sử dụng dịch vụ (hoặc Địa chỉ nếu là dịch vụ tại nhà)
   - Nếu khách chưa cung cấp Số điện thoại: Hãy ghi nhớ các thông tin khách đã nói, báo giá/tư vấn ngắn gọn và khéo léo xin Số điện thoại để giữ lịch/giữ suất ưu đãi.
   - CHỈ KHI khách đã cung cấp Số điện thoại hợp lệ: Xác nhận thông tin đã đặt, báo nhân viên phụ trách sẽ liên hệ xác nhận trong ít phút tới, đồng thời chèn thêm đúng 1 dòng thẻ kỹ thuật ở cuối cùng (không giải thích gì thêm về dòng này):
[CHOT_LICH: Tên khách | Số điện thoại | Dịch vụ/Gói | Thời gian/Địa chỉ]
"""

# 5. ĐƯỜNG DẪN KIỂM TRA SERVER SỐNG (DÙNG CHO UPTIMEROBOT)
@app.api_route("/", methods=["GET", "HEAD"])
@app.api_route("/health", methods=["GET", "HEAD"])
def health_check():
    return {"status": "ok"}

# 6. ĐƯỜNG DẪN NHẬN TIN NHẮN TỪ SMAX.BOT / PANCAKE
@app.post("/webhook")
async def nhan_tin_nhan(request: Request):
    try:
        du_lieu = await request.json()
    except Exception:
        form = await request.form()
        du_lieu = dict(form)

    print("DU LIEU SMAX GUI:", du_lieu)
    sender_id = str(
        du_lieu.get("sender_id")
        or du_lieu.get("user_id")
        or du_lieu.get("psid")
        or du_lieu.get("id")
        or "khach_vang_lai"
    )
    tin_nhan_khach = str(
        du_lieu.get("message")
        or du_lieu.get("text")
        or du_lieu.get("content")
        or du_lieu.get("last_user_input")
        or ""
    ).strip()

    if not tin_nhan_khach:
        return {"reply": "", "messages": []}

    if sender_id not in lich_su_hoi_thoai:
        lich_su_hoi_thoai[sender_id] = []
    lich_su_hoi_thoai[sender_id].append({"role": "user", "content": tin_nhan_khach})
    lich_su_hoi_thoai[sender_id] = lich_su_hoi_thoai[sender_id][-10:]

    messages_gui_ai = [{"role": "system", "content": SYSTEM_PROMPT}] + lich_su_hoi_thoai[sender_id]

    cau_tra_loi = ""
    for model_id in lay_danh_sach_model()[:4]:
        try:
            response = client.chat.completions.create(
                model=model_id,
                messages=messages_gui_ai,
                temperature=0.3,
                max_tokens=800,
                frequency_penalty=0.3,
            )
            noi_dung = response.choices[0].message.content or ""
            noi_dung = re.sub(r"<think>.*?</think>", "", noi_dung, flags=re.DOTALL).strip()
            if noi_dung:
                cau_tra_loi = noi_dung
                break
        except Exception:
            continue

    if not cau_tra_loi:
        cau_tra_loi = "Dạ hiện tại hệ thống đang hơi quá tải một chút, anh/chị cho em xin số điện thoại để chuyên viên bên em gọi tư vấn trực tiếp cho mình ngay ạ!"

    match = re.search(r"\[CHOT_LICH:\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\|\s*(.*?)\s*\]", cau_tra_loi)
    if match:
        luu_len_google_sheet(match.group(1), match.group(2), match.group(3), match.group(4), sender_id)
        cau_tra_loi = re.sub(r"\[CHOT_LICH:.*?\]", "", cau_tra_loi).strip()

    lich_su_hoi_thoai[sender_id].append({"role": "assistant", "content": cau_tra_loi})

    return {
        "reply": cau_tra_loi,
        "messages": [{"text": cau_tra_loi}],
        "version": "v2",
        "content": {
            "messages": [{"type": "text", "text": cau_tra_loi}]
        },
    }
