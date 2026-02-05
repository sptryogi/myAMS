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
    st.header("🔁 Seller Conversion Report (AMS v2)")
    
    shops = get_all_shops()
    if not shops:
        st.warning("Belum ada toko. Silakan authorize dan tukar token di Tab 1 & 2.")
        st.stop()
    
    selected_shop = st.selectbox("🏪 Pilih Toko", shops)
    
    # =====================================================
    # DATE RANGE SELECTOR (FLEXIBLE)
    # =====================================================
    st.subheader("📅 Periode Laporan")
    
    date_col1, date_col2, date_col3 = st.columns([2, 2, 1])
    
    with date_col1:
        # Preset cepat
        preset = st.selectbox(
            "Preset Cepat",
            ["Custom Range", "Hari Ini", "Kemarin", "7 Hari Terakhir", "30 Hari Terakhir", "Bulan Ini", "Bulan Lalu"],
            index=3
        )
    
    # Default values
    today = datetime.date.today()
    
    if preset == "Hari Ini":
        start_date = today
        end_date = today
    elif preset == "Kemarin":
        start_date = today - datetime.timedelta(days=1)
        end_date = today - datetime.timedelta(days=1)
    elif preset == "7 Hari Terakhir":
        start_date = today - datetime.timedelta(days=7)
        end_date = today
    elif preset == "30 Hari Terakhir":
        start_date = today - datetime.timedelta(days=30)
        end_date = today
    elif preset == "Bulan Ini":
        start_date = today.replace(day=1)
        end_date = today
    elif preset == "Bulan Lalu":
        first_day_this_month = today.replace(day=1)
        end_date = first_day_this_month - datetime.timedelta(days=1)
        start_date = end_date.replace(day=1)
    else:  # Custom Range
        with date_col2:
            start_date = st.date_input("Dari Tanggal", today - datetime.timedelta(days=7))
        with date_col3:
            end_date = st.date_input("Sampai Tanggal", today)
    
    # Display selected range
    delta_days = (end_date - start_date).days + 1
    st.info(f"📆 Periode: **{start_date.strftime('%d %b %Y')}** s/d **{end_date.strftime('%d %b %Y')}** ({delta_days} hari)")
    
    # Validate range (Shopee biasanya limit 30-90 hari)
    if delta_days > 90:
        st.warning("⚠️ Rentang waktu > 90 hari mungkin akan error dari API Shopee. Pertimbangkan untuk memecah periode.")
    
    # =====================================================
    # FETCH DATA
    # =====================================================
    if st.button("🚀 Tarik Data Conversion", type="primary"):
        token = get_shop_token(selected_shop)
        if not token:
            st.error("❌ Token tidak ditemukan. Silakan authorize ulang.")
            st.stop()
        
        shop_id = token["shop_id"]
        access_token = token["access_token"]
        
        # Helper: Convert date to timestamp
        def to_ts(d, end=False):
            dt = datetime.datetime.combine(d, datetime.time(23, 59, 59) if end else datetime.time(0, 0, 0))
            return int(dt.replace(tzinfo=datetime.timezone.utc).timestamp())
        
        start_ts = to_ts(start_date)
        end_ts = to_ts(end_date, end=True)
        
        # Progress tracking
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        path = "/api/v2/ams/get_conversion_report"
        page_no = 1
        page_size = 100  # Maximize page size
        all_orders = []
        
        with st.spinner("Mengambil data dari Shopee API..."):
            while True:
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
                    st.error(f"🌐 Network Error: {str(e)}")
                    break
                
                if resp.get("error"):
                    st.error(f"❌ API Error: {resp.get('message', 'Unknown error')}")
                    st.json(resp)
                    break
                
                data = resp.get("response", {})
                orders = data.get("list", [])
                
                if not orders:
                    break
                
                all_orders.extend(orders)
                
                # Update progress
                total_estimate = data.get("total_count", page_no * page_size)
                progress = min(page_no * page_size / max(total_estimate, 1), 0.95)
                progress_bar.progress(progress)
                status_text.text(f"📄 Page {page_no} | Orders: {len(all_orders)} | Items: {sum(len(o.get('items', [])) for o in all_orders)}")
                
                if not data.get("has_more", False):
                    break
                
                page_no += 1
                time.sleep(0.3)  # Rate limiting
        
        progress_bar.empty()
        status_text.empty()
        
        # =====================================================
        # PROCESS DATA
        # =====================================================
        if not all_orders:
            st.warning("📭 Tidak ada data conversion untuk periode ini.")
            st.info("💡 Tips: Coba perpanjang rentang tanggal atau cek apakah ada order completed.")
            st.stop()
        
        # Flatten data
        rows = []
        for order in all_orders:
            order_base = {
                "order_sn": order.get("order_sn"),
                "order_status": order.get("order_status"),
                "verified_status": order.get("verified_status"),
                "place_order_time": order.get("place_order_time"),
                "order_completed_time": order.get("order_completed_time"),
                "conversion_completed_time": order.get("conversion_completed_time"),
                "affiliate_id": order.get("affiliate_id"),
                "affiliate_name": order.get("affiliate_name"),
                "affiliate_username": order.get("affiliate_username"),
                "linked_mcn": order.get("linked_mcn"),
                "channel": order.get("channel"),
                "order_type": order.get("order_type"),
                "buyer_status": order.get("buyer_status"),
            }
            
            for item in order.get("items", []):
                row = order_base.copy()
                row.update({
                    # Item details
                    "item_id": item.get("item_id"),
                    "item_name": item.get("item_name"),
                    "model_id": item.get("model_id"),
                    "model_name": item.get("model_name"),
                    "l1_category_id": item.get("l1_category_id"),
                    "l2_category_id": item.get("l2_category_id"),
                    "l3_category_id": item.get("l3_category_id"),
                    "promotion_id": item.get("promotion_id"),
                    
                    # Quantity & Pricing
                    "qty": item.get("qty", 0),
                    "price": item.get("price", 0),
                    "purchase_value": item.get("purchase_value", 0),
                    "refund_amount": item.get("refund_amount", 0),
                    
                    # Commissions
                    "item_brand_commission": item.get("item_brand_commission", 0),
                    "commission_rate_to_affiliate": item.get("item_brand_commission_rate_to_affiliate", 0),
                    "commission_to_affiliate": item.get("item_brand_commission_to_affiliate", 0),
                    "commission_rate_to_mcn": item.get("item_brand_commission_rate_to_mcn", 0),
                    "commission_to_mcn": item.get("item_brand_commission_to_mcn", 0),
                    
                    # Campaign
                    "seller_campaign_type": item.get("seller_campaign_type"),
                    "attr_campaign_id": item.get("attr_campaign_id"),
                    "campaign_partner": item.get("campaign_partner"),
                })
                rows.append(row)
        
        # Create DataFrame
        df = pd.DataFrame(rows)
        
        # =====================================================
        # FIX: SAFE NUMERIC CONVERSION
        # =====================================================
        numeric_cols = {
            'qty': 0, 'price': 0.0, 'purchase_value': 0.0, 'refund_amount': 0.0,
            'item_brand_commission': 0.0, 'commission_rate_to_affiliate': 0.0,
            'commission_to_affiliate': 0.0, 'commission_rate_to_mcn': 0.0,
            'commission_to_mcn': 0.0
        }
        
        for col, default in numeric_cols.items():
            if col in df.columns:
                # Method aman: coerce errors ke NaN kemudian fillna
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(default)
        
        # Add calculated column: Pengeluaran(Rp)
        df['pengeluaran_rp'] = df['item_brand_commission']  # Total commission deducted
        
        # =====================================================
        # DISPLAY RESULTS
        # =====================================================
        st.success(f"✅ Berhasil! {len(df)} item dari {len(all_orders)} orders")
        
        # Metrics Summary
        metric_cols = st.columns(4)
        metrics = [
            ("💰 Total Purchase", df['purchase_value'].sum(), "Rp {:,.0f}"),
            ("💸 Total Pengeluaran", df['pengeluaran_rp'].sum(), "Rp {:,.0f}"),
            ("👥 Ke Affiliate", df['commission_to_affiliate'].sum(), "Rp {:,.0f}"),
            ("🏢 Ke MCN", df['commission_to_mcn'].sum(), "Rp {:,.0f}")
        ]
        
        for col, (label, value, fmt) in zip(metric_cols, metrics):
            with col:
                st.metric(label, fmt.format(value))
        
        # Reorder columns untuk display
        display_cols = [
            'order_sn', 'place_order_time', 'item_name', 'purchase_value',
            'pengeluaran_rp', 'commission_to_affiliate', 'commission_to_mcn',
            'affiliate_name', 'channel', 'qty', 'price'
        ]
        # Add remaining columns
        display_cols = [c for c in display_cols if c in df.columns] + [c for c in df.columns if c not in display_cols]
        df_display = df[display_cols]
        
        # Rename columns untuk UI lebih baik
        column_mapping = {
            'order_sn': 'Order SN',
            'place_order_time': 'Waktu Order',
            'item_name': 'Nama Produk',
            'purchase_value': 'Nilai Beli (Rp)',
            'pengeluaran_rp': 'Pengeluaran (Rp)',
            'commission_to_affiliate': 'Komisi Affiliate (Rp)',
            'commission_to_mcn': 'Komisi MCN (Rp)',
            'affiliate_name': 'Nama Affiliate',
            'channel': 'Channel',
            'qty': 'Qty',
            'price': 'Harga Satuan'
        }
        df_display = df_display.rename(columns=column_mapping)
        
        st.dataframe(df_display, use_container_width=True, height=500)
        
        # =====================================================
        # EXPORT EXCEL
        # =====================================================
        st.divider()
        st.subheader("📥 Export Data")
        
        # Prepare export data (all columns, original names)
        export_df = df.copy()
        
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            export_df.to_excel(writer, index=False, sheet_name='AMS Conversion')
            
            # Auto-adjust
            worksheet = writer.sheets['AMS Conversion']
            for column in worksheet.columns:
                max_length = max(len(str(cell.value) or "") for cell in column) + 2
                worksheet.column_dimensions[column[0].column_letter].width = min(max_length, 50)
        
        excel_data = excel_buffer.getvalue()
        
        exp_col1, exp_col2, exp_col3 = st.columns([1, 1, 2])
        
        with exp_col1:
            st.download_button(
                label="📥 Download Excel",
                data=excel_data,
                file_name=f"AMS_{selected_shop}_{start_date}_{end_date}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        
        with exp_col2:
            if st.button("💾 Simpan ke Database"):
                try:
                    save_report_to_db(selected_shop, f"{start_date} to {end_date}", excel_data)
                    st.success("✅ Tersimpan!")
                except Exception as e:
                    st.error(f"Gagal simpan: {e}")
        
        with exp_col3:
            with st.expander("🔍 Lihat Sample Data Raw (JSON)"):
                st.json(all_orders[0] if all_orders else {})
                            
