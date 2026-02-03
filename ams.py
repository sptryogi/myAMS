# myAMS - Shopee AMS Affiliate App (Tab 1, 2, 6 Only)
# NOTE: Helper functions & DB logic are preserved

import streamlit as st
import base64
import time
import hmac
import hashlib
import urllib.parse
import requests
import pandas as pd
import datetime
import io
from supabase import create_client, Client

# ===============================
# PAGE CONFIG
# ===============================
st.set_page_config(page_title="myAMS - Shopee Affiliate AMS", layout="wide")

# ===============================
# SUPABASE CONFIG
# ===============================
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ===============================
# SHOPEE CONFIG (AFFILIATE APP)
# ===============================
PARTNER_ID = st.secrets.get("PARTNER_ID", "")
PARTNER_KEY = st.secrets.get("PARTNER_KEY", "")
REDIRECT_URL = st.secrets.get("REDIRECT_URL", "")
BASE_URL = "https://partner.shopeemobile.com"

# ===============================
# OAUTH PARAMS
# ===============================
query_params = st.experimental_get_query_params()
oauth_code = query_params.get("code", [None])[0]
oauth_shop_id = query_params.get("shop_id", [None])[0]

# ===============================
# SIGNATURE HELPERS
# ===============================
def generate_sign_basic(path, timestamp):
    base = f"{PARTNER_ID}{path}{timestamp}"
    return hmac.new(PARTNER_KEY.encode(), base.encode(), hashlib.sha256).hexdigest()

def generate_sign_full(path, timestamp, access_token, shop_id):
    base = f"{PARTNER_ID}{path}{timestamp}{access_token}{shop_id}"
    return hmac.new(PARTNER_KEY.encode(), base.encode(), hashlib.sha256).hexdigest()

# ===============================
# DB HELPERS (UNCHANGED)
# ===============================
def save_token_to_db(shop_name, shop_id, access_token, refresh_token):
    supabase.table("shopee_tokens").upsert({
        "shop_name": shop_name,
        "shop_id": int(shop_id),
        "access_token": access_token,
        "refresh_token": refresh_token,
        "updated_at": "now()"
    }).execute()

def get_all_shops():
    res = supabase.table("shopee_tokens").select("shop_name").execute()
    return [r["shop_name"] for r in res.data] if res.data else []

def get_shop_token(shop_name):
    res = supabase.table("shopee_tokens").select("*").eq("shop_name", shop_name).execute()
    return res.data[0] if res.data else None

def save_report_to_db(shop_name, date_range, excel_bytes):
    supabase.table("shopee_reports").insert({
        "shop_name": shop_name,
        "date_range": date_range,
        "csv_content": base64.b64encode(excel_bytes).decode(),
        "created_at": "now()"
    }).execute()

# ===============================
# UI
# ===============================
st.title("📊 myAMS - Shopee Affiliate Conversion")

tab1, tab2, tab6 = st.tabs([
    "1️⃣ Authorisasi Affiliate",
    "2️⃣ Tukar Code → Token",
    "6️⃣ Seller Conversion (AMS)"
])

# ===============================
# TAB 1 — AUTHORISASI
# ===============================
with tab1:
    st.header("Generate Authorization URL (Affiliate App)")

    if st.button("🔐 Generate Authorization URL"):
        path = "/api/v2/shop/auth_partner"
        ts = int(time.time())
        sign = generate_sign_basic(path, ts)

        params = {
            "partner_id": PARTNER_ID,
            "timestamp": ts,
            "sign": sign,
            "redirect": REDIRECT_URL
        }

        auth_url = BASE_URL + path + "?" + urllib.parse.urlencode(params)
        st.success("Gunakan URL ini untuk authorize Affiliate / Seller")
        st.code(auth_url)

# ===============================
# TAB 2 — TOKEN
# ===============================
with tab2:
    st.header("Tukar Code ke Access Token")

    code = st.text_input("Code", value=oauth_code or "")
    shop_id = st.text_input("Shop ID", value=oauth_shop_id or "")
    shop_name = st.text_input("Nama Toko", "MyAffiliateShop")

    if st.button("🔄 Tukar Token"):
        path = "/api/v2/auth/token/get"
        ts = int(time.time())
        sign = generate_sign_basic(path, ts)

        res = requests.post(
            BASE_URL + path,
            params={"partner_id": PARTNER_ID, "timestamp": ts, "sign": sign},
            json={"code": code, "shop_id": int(shop_id), "partner_id": int(PARTNER_ID)}
        ).json()

        st.json(res)

        if "access_token" in res:
            save_token_to_db(shop_name, shop_id, res["access_token"], res["refresh_token"])
            st.success("Token Affiliate berhasil disimpan")

# ===============================
# TAB 6 — AMS CONVERSION
# ===============================
with tab6:
    st.header("🔁 Seller Conversion")
    st.info("Menarik data seller conversion / affiliate conversion menggunakan API AMS Shopee.")

    if not shop_name:
        st.warning("Belum ada toko.")
    else:
        selected_shop_conv = st.selectbox("Pilih Toko untuk Conversion", shop_names, key="shop_conv")

        col_c1, col_c2 = st.columns(2)
        with col_c1:
            start_conv = st.date_input("Dari Tanggal", datetime.date.today() - datetime.timedelta(days=7), key="s_conv")
        with col_c2:
            end_conv = st.date_input("Sampai Tanggal", datetime.date.today(), key="e_conv")

        if st.button("📊 Tarik Seller Conversion"):
            token_row = get_shop_token(selected_shop_conv)
            if not token_row:
                st.error("Token tidak ditemukan.")
            else:
                ACTIVE_SHOP_ID = token_row["shop_id"]
                ACTIVE_ACCESS_TOKEN = token_row["access_token"]

                # Konversi ke Timestamp (00:00:00 s/d 23:59:59)
                time_from = int(time.mktime(start_conv.timetuple()))
                time_to = int(time.mktime(end_conv.timetuple())) + 86399

                # API Path untuk AMS Conversion Report
                path_conv = "/api/v2/ams/get_conversion_report"
                
                all_conv_data = []
                cursor = ""
                has_more = True
                
                prog_conv = st.progress(0)
                status_text = st.empty()
                
                # Mapping Status agar sesuai Dashboard Indonesia
                status_map = {
                    "UNPAID": "Belum Dibayar",
                    "READY_TO_SHIP": "Sedang Diproses",
                    "PROCESSED": "Sedang Diproses",
                    "SHIPPED": "Sedang Diproses",
                    "COMPLETED": "Selesai",
                    "CANCELLED": "Dibatalkan",
                    "IN_CANCEL": "Dibatalkan",
                    "TO_CONFIRM_RECEIVE": "Sedang Diproses"
                }

                while has_more:
                    ts_conv = int(time.time())
                    sign_conv = generate_sign_full(path_conv, ts_conv, ACTIVE_ACCESS_TOKEN, ACTIVE_SHOP_ID)

                    params = {
                        "partner_id": PARTNER_ID,
                        "timestamp": ts_conv,
                        "access_token": ACTIVE_ACCESS_TOKEN,
                        "shop_id": int(ACTIVE_SHOP_ID),
                        "sign": sign_conv,
                        "purchase_time_from": time_from,
                        "purchase_time_to": time_to,
                        "page_size": 50,
                        "cursor": cursor
                    }

                    try:
                        resp = requests.get(BASE_URL + path_conv, params=params).json()
                        
                        if resp.get("error"):
                            st.error(f"Error API: {resp.get('message')}")
                            break
                        
                        res_data = resp.get("response", {})
                        report_list = res_data.get("report_list", [])
                        
                        if not report_list:
                            break

                        for item in report_list:
                            raw_status = item.get("order_status", "").upper()

                            if raw_status != "COMPLETED":
                                continue
                                
                            status_indo = status_map.get(raw_status, raw_status)

                            
                            # Logika Status Terverifikasi (Sesuai Sample: COMPLETED -> Verified)
                            verified_status = "Verified" if raw_status == "COMPLETED" else "Belum Diverifikasi"

                            # Helper format tanggal
                            def fmt_ts(ts):
                                if not ts or ts == 0: return ""
                                return pd.to_datetime(ts, unit='s').strftime('%Y-%m-%d %H:%M:%S')

                            # Mapping Field Sesuai File SellerConversionReport.csv
                            all_conv_data.append({
                                "Kode Pesanan": item.get("order_sn"),
                                "Status Pesanan": status_indo,
                                "Status Terverifikasi": verified_status,
                                "Waktu Pesanan": fmt_ts(item.get("purchase_time")),
                                "Waktu Pesanan Selesai": fmt_ts(item.get("finish_time")),
                                "Waktu Pesanan Terverifikasi": fmt_ts(item.get("validation_time")),
                                "Kode Produk": item.get("item_id"),
                                "Nama Produk": item.get("item_name"),
                                "ID Model": item.get("model_id"),
                                "L1 Kategori Global": item.get("category_l1", ""),
                                "L2 Kategori Global": item.get("category_l2", ""),
                                "L3 Kategori Global": item.get("category_l3", ""),
                                "Kode Promo": item.get("promo_code", ""),
                                "Harga(Rp)": item.get("item_price", 0),
                                "Jumlah": item.get("item_count", 0),
                                "Nama Affiliate": item.get("affiliate_name", ""),
                                "Username Affiliate": item.get("affiliate_username", ""),
                                "MCN Terhubung": item.get("mcn_name", ""),
                                "ID Komisi Pesanan": item.get("commission_id", ""),
                                "Partner Promo": item.get("partner_promo", ""),
                                "Jenis Promo": item.get("promo_type", ""),
                                "Nilai Pembelian(Rp)": item.get("total_item_price", 0),
                                "Jumlah Pengembalian(Rp)": item.get("refund_amount", 0),
                                "Tipe Pesanan": "Pesanan Langsung" if item.get("order_type") == "DIRECT" else "Pesanan Tidak Langsung",
                                "Estimasi Komisi per Produk(Rp)": item.get("item_commission", 0),
                                "Estimasi Komisi Affiliate per Produk(Rp)": item.get("item_affiliate_commission", 0),
                                "Persentase Komisi Affiliate per Produk": f"{item.get('item_affiliate_commission_rate', 0)}%",
                                "Estimasi Komisi MCN per Produk(Rp)": item.get("item_mcn_commission", 0),
                                "Persentase Komisi MCN per Produk": f"{item.get('item_mcn_commission_rate', 0)}%",
                                "Estimasi Komisi per Pesanan(Rp)": item.get("order_commission", 0),
                                "Estimasi Komisi Affiliate per Pesanan(Rp)": item.get("order_affiliate_commission", 0),
                                "Estimasi Komisi MCN per Pesanan(Rp)": item.get("order_mcn_commission", 0),
                                "Catatan Produk": item.get("product_note", ""),
                                "Platform": item.get("platform", "Shopee"),
                                "Pengeluaran(Rp)": item.get("total_expense", 0),
                                "Status Pemotongan": item.get("deduction_status", ""),
                                "Metode Pemotongan": item.get("deduction_method", ""),
                                "Waktu Pemotongan": fmt_ts(item.get("deduction_time"))
                            })

                        status_text.info(f"Mengambil data... (Total sementara: {len(all_conv_data)})")
                        
                        # Pagination: Jika next_cursor ada, lanjut ambil data berikutnya
                        cursor = res_data.get("next_cursor", "")
                        if not cursor or not res_data.get("has_next_page"):
                            has_more = False
                        
                        time.sleep(0.4) # Jeda untuk menghindari rate limit
                    except Exception as e:
                        st.error(f"Gagal memproses API: {str(e)}")
                        break

                if all_conv_data:
                    df_conv = pd.DataFrame(all_conv_data)
                    st.success(f"Berhasil menarik total {len(df_conv)} baris data.")
                    st.dataframe(df_conv)

                    # Export ke Excel
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                        df_conv.to_excel(writer, index=False, sheet_name='Seller Conversion')
                    excel_data = output.getvalue()

                    st.download_button(
                        label="📥 Download Seller Conversion (Excel)",
                        data=excel_data,
                        file_name=f"Seller_Conversion_{selected_shop_conv}_{start_conv}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.warning("Tidak ada data conversion ditemukan untuk periode ini.")
        # ===============================
        # RIWAYAT CONVERSION
        # ===============================
        st.divider()
        st.subheader("📜 Riwayat Seller Conversion (Database)")

        history_conv = get_report_history(selected_shop_conv)

        if not history_conv:
            st.write("Belum ada riwayat seller conversion.")
        else:
            for item in history_conv:
                if not item["date_range"].startswith("CONVERSION"):
                    continue

                col1, col2, col3 = st.columns([3, 3, 2])
                col1.write(f"📅 {item['date_range']}")
                col2.write(f"⏰ {item['created_at'][:19]}")
                col3.download_button(
                    label="💾 Download Excel",
                    data=item["csv_content"],
                    file_name=f"Seller_Conversion_{selected_shop_conv}_{item['created_at'][:10]}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key=f"conv_{item['id']}"
                )
