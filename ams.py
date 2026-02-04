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

def get_report_history(shop_name):
    res = supabase.table("shopee_reports").select("*").eq("shop_name", shop_name).order("created_at", desc=True).limit(10).execute()
    return res.data
    
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
# ===============================
# TAB 6 — AMS CONVERSION (FIXED)
# ===============================
with tab6:
    st.header("🔁 Seller Conversion (AMS v2)")
    st.info("Mengambil data conversion sesuai dokumentasi resmi Shopee AMS v2.")

    shops = get_all_shops()
    if not shops:
        st.warning("Belum ada toko.")
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

                rows = []
                progress = st.progress(0)
                info = st.empty()

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

                    resp = requests.get(BASE_URL + path, params=params).json()

                    if resp.get("error"):
                        st.error(f"API Error: {resp.get('message')}")
                        break

                    data = resp.get("response", {})
                    orders = data.get("list", [])

                    if not orders:
                        break

                    for order in orders:
                        for item in order.get("items", []):
                            rows.append({
                                "Order SN": order.get("order_sn"),
                                "Order Status": order.get("order_status"),
                                "Verified Status": order.get("verified_status"),
                                "Place Order Time": order.get("place_order_time"),
                                "Order Completed Time": order.get("order_completed_time"),
                                "Conversion Completed Time": order.get("conversion_completed_time"),

                                "Affiliate ID": order.get("affiliate_id"),
                                "Affiliate Name": order.get("affiliate_name"),
                                "Affiliate Username": order.get("affiliate_username"),
                                "Linked MCN": order.get("linked_mcn"),
                                "Channel": order.get("channel"),
                                "Order Type": order.get("order_type"),
                                "Buyer Status": order.get("buyer_status"),

                                "Item ID": item.get("item_id"),
                                "Item Name": item.get("item_name"),
                                "Model ID": item.get("model_id"),
                                "L1 Category ID": item.get("l1_category_id"),
                                "L2 Category ID": item.get("l2_category_id"),
                                "L3 Category ID": item.get("l3_category_id"),
                                "Promotion ID": item.get("promotion_id"),

                                "Item Price": item.get("price"),
                                "Qty": item.get("qty"),
                                "Purchase Value": item.get("purchase_value"),
                                "Refund Amount": item.get("refund_amount"),

                                "Item Brand Commission": item.get("item_brand_commission"),
                                "Commission Rate to Affiliate": item.get("item_brand_commission_rate_to_affiliate"),
                                "Commission to Affiliate": item.get("item_brand_commission_to_affiliate"),
                                "Commission Rate to MCN": item.get("item_brand_commission_rate_to_mcn"),
                                "Commission to MCN": item.get("item_brand_commission_to_mcn"),

                                "Seller Campaign Type": item.get("seller_campaign_type"),
                                "Attr Campaign ID": item.get("attr_campaign_id"),
                                "Campaign Partner": item.get("campaign_partner")
                            })

                    has_more = data.get("has_more", False)
                    page_no += 1
                    progress.progress(min(page_no / 20, 1.0))
                    info.info(f"Page {page_no - 1} • Total baris: {len(rows)}")

                    time.sleep(0.4)

                if rows:
                    df = pd.DataFrame(rows)
                    st.success(f"Berhasil mengambil {len(df)} baris data.")
                    st.dataframe(df, use_container_width=True)

                    output = io.BytesIO()
                    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
                        df.to_excel(writer, index=False, sheet_name="AMS Conversion")

                    st.download_button(
                        "📥 Download Excel",
                        data=output.getvalue(),
                        file_name=f"AMS_Conversion_{selected_shop}_{start_date}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                    )
                else:
                    st.warning("Tidak ada data conversion ditemukan.")
