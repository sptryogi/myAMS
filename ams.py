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
# OAUTH PARAMS (AUTO-FILL SUPPORT)
# ===============================
# Gunakan st.query_params yang baru, bukan experimental
query_params = st.query_params
oauth_code = query_params.get("code", "")
oauth_shop_id = query_params.get("shop_id", "")

# Simpan ke session state agar persist ke Tab 2
if "oauth_code" not in st.session_state:
    st.session_state.oauth_code = oauth_code if oauth_code else ""
if "oauth_shop_id" not in st.session_state:
    st.session_state.oauth_shop_id = oauth_shop_id if oauth_shop_id else ""

# Update session state jika ada params baru di URL
if oauth_code:
    st.session_state.oauth_code = oauth_code
if oauth_shop_id:
    st.session_state.oauth_shop_id = oauth_shop_id

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

def get_report_history(shop_name):
    res = supabase.table("shopee_reports").select("*").eq("shop_name", shop_name).order("created_at", desc=True).limit(10).execute()
    return res.data
    
# ===============================
# UI
# ===============================
st.title("📊 myAMS - Shopee Affiliate Conversion")

# Notifikasi otomatis jika ada code dari redirect
if st.session_state.oauth_code and st.session_state.oauth_shop_id:
    st.success(f"✅ Authorization berhasil! Code dan Shop ID otomatis terisi di Tab 2. Code: {st.session_state.oauth_code[:20]}...")

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
        st.info("Setelah authorize, Anda akan di-redirect kembali ke app dengan code otomatis terisi di Tab 2.")

# ===============================
# TAB 2 — TOKEN (AUTO-FILL DARI OAUTH)
# ===============================
with tab2:
    st.header("Tukar Code ke Access Token")
    
    # Gunakan session state untuk auto-fill dari URL params
    code = st.text_input("Code", value=st.session_state.oauth_code)
    shop_id = st.text_input("Shop ID", value=st.session_state.oauth_shop_id)
    shop_name = st.text_input("Nama Toko", "MyAffiliateShop")

    # Tombol clear session jika perlu input manual
    col1, col2 = st.columns([1, 3])
    with col1:
        if st.button("🔄 Tukar Token"):
            if not code or not shop_id:
                st.error("Code dan Shop ID harus diisi!")
            else:
                path = "/api/v2/auth/token/get"
                ts = int(time.time())
                sign = generate_sign_basic(path, ts)

                try:
                    res = requests.post(
                        BASE_URL + path,
                        params={"partner_id": PARTNER_ID, "timestamp": ts, "sign": sign},
                        json={"code": code, "shop_id": int(shop_id), "partner_id": int(PARTNER_ID)}
                    ).json()

                    st.json(res)

                    if "access_token" in res:
                        save_token_to_db(shop_name, shop_id, res["access_token"], res["refresh_token"])
                        st.success(f"✅ Token Affiliate berhasil disimpan untuk toko: {shop_name}")
                        # Clear session state setelah berhasil
                        st.session_state.oauth_code = ""
                        st.session_state.oauth_shop_id = ""
                    else:
                        st.error(f"Gagal mendapatkan token: {res.get('message', 'Unknown error')}")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    with col2:
        if st.button("🧹 Clear Auto-fill Data"):
            st.session_state.oauth_code = ""
            st.session_state.oauth_shop_id = ""
            st.rerun()

# ===============================
# TAB 6 — AMS CONVERSION (ALL COLUMNS)
# ===============================
with tab6:
    st.header("🔁 Seller Conversion (AMS v2)")
    st.info("Mengambil SEMUA data conversion termasuk kolom komisi dan pengeluaran.")

    shops = get_all_shops()
    if not shops:
        st.warning("Belum ada toko. Silakan authorize dan tukar token terlebih dahulu di Tab 1 & 2.")
    else:
        selected_shop = st.selectbox("Pilih Toko", shops)

        col1, col2 = st.columns(2)
        with col1:
            start_date = st.date_input("Dari Tanggal", datetime.date.today() - datetime.timedelta(days=7))
        with col2:
            end_date = st.date_input("Sampai Tanggal", datetime.date.today())

        def to_ts(d, end=False):
            if end:
                dt = datetime.datetime.combine(d, datetime.time(23, 59, 59))
            else:
                dt = datetime.datetime.combine(d, datetime.time(0, 0, 0))
            return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp())

        if st.button("📊 Tarik Seller Conversion"):
            token = get_shop_token(selected_shop)
            if not token:
                st.error("Token tidak ditemukan.")
            else:
                shop_id = token["shop_id"]
                access_token = token["access_token"]

                start_ts = to_ts(start_date)
                end_ts = to_ts(end_date, end=True)

                path = "/api/v2/ams/get_conversion_report"
                page_no = 1
                page_size = 50
                has_more = True

                all_orders = []  # Simpan raw data untuk debug
                rows = []
                progress = st.progress(0)
                status_text = st.empty()

                while has_more:
                    ts = int(time.time())
                    sign = generate_sign_full(path, ts, access_token, shop_id)

                    params = {
                        "partner_id": PARTNER_ID,
                        "timestamp": ts,
                        "access_token": access_token,
                        "shop_id": int(shop_id),
                        "sign": sign,
                        "page_no": page_no,
                        "page_size": page_size,
                        "place_order_time_start": start_ts,
                        "place_order_time_end": end_ts,
                        "order_status": "Completed"
                    }

                    try:
                        resp = requests.get(BASE_URL + path, params=params, timeout=30).json()
                    except Exception as e:
                        st.error(f"Request error: {str(e)}")
                        break

                    if resp.get("error"):
                        st.error(f"API Error: {resp.get('message', 'Unknown error')}")
                        st.json(resp)
                        break

                    data = resp.get("response", {})
                    orders = data.get("list", [])
                    
                    if not orders:
                        break

                    all_orders.extend(orders)  # Simpan untuk debug

                    for order in orders:
                        # Ambil semua field dari order level
                        order_sn = order.get("order_sn")
                        order_status = order.get("order_status")
                        verified_status = order.get("verified_status")
                        place_order_time = order.get("place_order_time")
                        order_completed_time = order.get("order_completed_time")
                        conversion_completed_time = order.get("conversion_completed_time")
                        
                        affiliate_id = order.get("affiliate_id")
                        affiliate_name = order.get("affiliate_name")
                        affiliate_username = order.get("affiliate_username")
                        linked_mcn = order.get("linked_mcn")
                        channel = order.get("channel")
                        order_type = order.get("order_type")
                        buyer_status = order.get("buyer_status")
                        
                        # Total level order (untuk referensi)
                        total_brand_commission = order.get("total_brand_commission", 0)
                        total_brand_commission_to_affiliate = order.get("total_brand_commission_to_affiliate", 0)
                        total_brand_commission_to_mcn = order.get("total_brand_commission_to_mcn", 0)

                        for item in order.get("items", []):
                            # Kalkulasi Pengeluaran (Commission yang harus dibayar seller)
                            # Ini adalah komisi total yang keluar dari seller
                            item_brand_commission = item.get("item_brand_commission", 0) or 0
                            commission_to_affiliate = item.get("item_brand_commission_to_affiliate", 0) or 0
                            commission_to_mcn = item.get("item_brand_commission_to_mcn", 0) or 0
                            
                            # Pengeluaran = Total komisi yang dibayarkan (biasanya ke affiliate + mcn)
                            # Atau bisa juga menggunakan item_brand_commission (total potongan)
                            pengeluaran_rp = item_brand_commission  # atau commission_to_affiliate + commission_to_mcn

                            row_data = {
                                # Order Info
                                "Order SN": order_sn,
                                "Order Status": order_status,
                                "Verified Status": verified_status,
                                "Place Order Time": place_order_time,
                                "Order Completed Time": order_completed_time,
                                "Conversion Completed Time": conversion_completed_time,
                                
                                # Affiliate Info
                                "Affiliate ID": affiliate_id,
                                "Affiliate Name": affiliate_name,
                                "Affiliate Username": affiliate_username,
                                "Linked MCN": linked_mcn,
                                "Channel": channel,
                                "Order Type": order_type,
                                "Buyer Status": buyer_status,
                                
                                # Item Info
                                "Item ID": item.get("item_id"),
                                "Item Name": item.get("item_name"),
                                "Model ID": item.get("model_id"),
                                "Model Name": item.get("model_name"),  # Tambahan
                                "L1 Category ID": item.get("l1_category_id"),
                                "L2 Category ID": item.get("l2_category_id"),
                                "L3 Category ID": item.get("l3_category_id"),
                                "Promotion ID": item.get("promotion_id"),
                                
                                # Pricing & Quantity
                                "Item Price": item.get("price"),
                                "Qty": item.get("qty"),
                                "Purchase Value": item.get("purchase_value"),
                                "Refund Amount": item.get("refund_amount"),
                                
                                # Commission Details (SEMUA KOLOM KOMISI)
                                "Item Brand Commission": item_brand_commission,
                                "Commission Rate to Affiliate": item.get("item_brand_commission_rate_to_affiliate"),
                                "Commission to Affiliate": commission_to_affiliate,
                                "Commission Rate to MCN": item.get("item_brand_commission_rate_to_mcn"),
                                "Commission to MCN": commission_to_mcn,
                                
                                # PENGELUARAN (Rp) - Kolom yang Anda minta
                                "Pengeluaran(Rp)": pengeluaran_rp,
                                
                                # Campaign Info
                                "Seller Campaign Type": item.get("seller_campaign_type"),
                                "Attr Campaign ID": item.get("attr_campaign_id"),
                                "Campaign Partner": item.get("campaign_partner"),
                                
                                # Tambahan field lain yang mungkin ada
                                "Shop ID": shop_id,
                                "Page": page_no
                            }
                            rows.append(row_data)

                    has_more = data.get("has_more", False)
                    total_count = data.get("total_count", 0)
                    
                    progress.progress(min(page_no * page_size / max(total_count, 1), 1.0))
                    status_text.info(f"Page {page_no} | Rows: {len(rows)} | Has More: {has_more}")
                    
                    page_no += 1
                    time.sleep(0.5)  # Rate limiting

                if rows:
                    df = pd.DataFrame(rows)
                    
                    # Reorder columns untuk UX lebih baik
                    priority_cols = [
                        "Order SN", "Place Order Time", "Item Name", "Purchase Value", 
                        "Pengeluaran(Rp)", "Commission to Affiliate", "Commission to MCN",
                        "Item Brand Commission", "Affiliate Name", "Channel"
                    ]
                    other_cols = [c for c in df.columns if c not in priority_cols]
                    df = df[priority_cols + other_cols]
                    
                    st.success(f"✅ Berhasil mengambil {len(df)} baris data dari {len(all_orders)} orders.")
                    
                    # Summary metrics
                    metric_col1, metric_col2, metric_col3 = st.columns(3)
                    with metric_col1:
                        st.metric("Total Purchase Value", f"Rp {df['Purchase Value'].sum():,.0f}")
                    with metric_col2:
                        st.metric("Total Pengeluaran", f"Rp {df['Pengeluaran(Rp)'].sum():,.0f}")
                    with metric_col3:
                        st.metric("Total Commission to Affiliate", f"Rp {df['Commission to Affiliate'].sum():,.0f}")
                    
                    st.dataframe(df, use_container_width=True, height=600)

                    # Export Excel
                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine="openpyxl") as writer:
                        df.to_excel(writer, index=False, sheet_name="AMS Conversion")
                        
                        # Auto-adjust column widths
                        worksheet = writer.sheets["AMS Conversion"]
                        for column in worksheet.columns:
                            max_length = 0
                            column_letter = column[0].column_letter
                            for cell in column:
                                try:
                                    if len(str(cell.value)) > max_length:
                                        max_length = len(str(cell.value))
                                except:
                                    pass
                            adjusted_width = min(max_length + 2, 50)
                            worksheet.column_dimensions[column_letter].width = adjusted_width

                    excel_data = output.getvalue()
                    
                    col_dl1, col_dl2 = st.columns(2)
                    with col_dl1:
                        st.download_button(
                            "📥 Download Excel",
                            data=excel_data,
                            file_name=f"AMS_Conversion_{selected_shop}_{start_date}_{end_date}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    with col_dl2:
                        # Simpan ke DB juga
                        if st.button("💾 Simpan ke Database"):
                            save_report_to_db(selected_shop, f"{start_date} to {end_date}", excel_data)
                            st.success("Report tersimpan di database!")
                    
                    # Debug: Tampilkan sample raw response
                    with st.expander("🔍 Debug: Sample Raw Data (Order 1)"):
                        if all_orders:
                            st.json(all_orders[0])
                            
                else:
                    st.warning("Tidak ada data conversion ditemukan.")
                    # Debug info
                    st.info("Tips: Coba ubah rentang tanggal atau cek apakah ada order completed di periode tersebut.")
