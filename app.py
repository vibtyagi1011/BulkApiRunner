"""
Bulk API Runner — Upload Excel, configure API, fire requests row by row.
No CORS issues — requests go directly from the server.

Run: streamlit run app.py
"""

import streamlit as st
import pandas as pd
import requests
import json
import time
import io
import csv

st.set_page_config(page_title="Bulk API Runner", page_icon="🚀", layout="wide")

# ── Custom CSS ──
st.markdown("""
<style>
    .stApp { }
    .block-container { max-width: 1100px; padding-top: 2rem; }
    .metric-card {
        background: #f0fdf4; border-radius: 10px; padding: 16px 20px;
        border-left: 4px solid #059669; margin-bottom: 8px;
    }
    .metric-card.fail { background: #fef2f2; border-left-color: #dc2626; }
    .metric-card h3 { margin: 0; font-size: 28px; color: #059669; }
    .metric-card.fail h3 { color: #dc2626; }
    .metric-card p { margin: 0; font-size: 13px; color: #6b7280; }
    div[data-testid="stExpander"] { border: 1px solid #e5e7eb; border-radius: 10px; }
</style>
""", unsafe_allow_html=True)

st.title("🚀 Bulk API Runner")
st.caption("Upload an Excel or CSV file, configure your API, and fire requests row by row — like Postman's Collection Runner.")

# ══════════════════════════════════════════════
# STEP 1: FILE UPLOAD
# ══════════════════════════════════════════════
st.markdown("### 1️⃣ Upload data file")
uploaded_file = st.file_uploader("Drop .xlsx, .xls, or .csv file", type=["xlsx", "xls", "csv"])

df = None
if uploaded_file:
    try:
        if uploaded_file.name.endswith(".csv"):
            df = pd.read_csv(uploaded_file)
        else:
            df = pd.read_excel(uploaded_file)
        st.success(f"✓ Loaded **{len(df)} rows** × **{len(df.columns)} columns** from `{uploaded_file.name}`")
        with st.expander("📋 Data preview (first 10 rows)", expanded=False):
            st.dataframe(df.head(10), use_container_width=True, height=300)
    except Exception as e:
        st.error(f"Error reading file: {e}")

# ══════════════════════════════════════════════
# STEP 2: API CONFIG
# ══════════════════════════════════════════════
st.markdown("### 2️⃣ API configuration")

col1, col2 = st.columns([1, 4])
with col1:
    method = st.selectbox("Method", ["POST", "PUT", "PATCH", "GET", "DELETE"])
with col2:
    endpoint = st.text_input("Endpoint URL", placeholder="https://api.nopaperforms.io/application/v1/list")

headers_json = st.text_area(
    "Headers (JSON)",
    value='{\n  "Content-Type": "application/json",\n  "secret-key": "",\n  "access-key": ""\n}',
    height=120
)

static_body = st.text_area(
    "Static JSON body (merged with every row)",
    value="{}",
    height=200,
    help="This JSON is merged with each row's data before sending. Use this for fixed fields like form_id, page_size, etc."
)

col_delay, _ = st.columns([1, 3])
with col_delay:
    delay_ms = st.number_input("Delay between requests (ms)", min_value=0, max_value=30000, value=200, step=50)

# ══════════════════════════════════════════════
# STEP 3: COLUMN MAPPING
# ══════════════════════════════════════════════
if df is not None:
    st.markdown("### 3️⃣ Column → JSON key mapping")
    st.caption("Each Excel column maps to a JSON key. Edit the right column to rename. Leave blank to skip.")

    if "col_map" not in st.session_state or st.session_state.get("_file_name") != uploaded_file.name:
        st.session_state.col_map = {col: col for col in df.columns}
        st.session_state._file_name = uploaded_file.name

    mapping_cols = st.columns(2)
    with mapping_cols[0]:
        st.markdown("**Excel Column**")
    with mapping_cols[1]:
        st.markdown("**JSON Key** (edit to rename, blank to skip)")

    new_map = {}
    for col in df.columns:
        mc1, mc2 = st.columns(2)
        with mc1:
            st.text(col)
        with mc2:
            new_key = st.text_input(
                f"key_{col}", value=st.session_state.col_map.get(col, col),
                label_visibility="collapsed", key=f"map_{col}"
            )
            new_map[col] = new_key.strip()
    st.session_state.col_map = new_map

    # Build payload function
    def build_row(row_data):
        payload = {}
        try:
            payload = json.loads(static_body) if static_body.strip() else {}
        except:
            pass
        for col, key in st.session_state.col_map.items():
            if key:
                val = row_data.get(col, "")
                if pd.isna(val):
                    val = ""
                payload[key] = val
        return payload

    # Preview
    st.markdown("### 4️⃣ Preview & Run")
    if len(df) > 0:
        preview = build_row(df.iloc[0].to_dict())
        with st.expander("🔍 JSON preview — Row 1", expanded=True):
            st.code(json.dumps(preview, indent=2, default=str), language="json")

    # ══════════════════════════════════════════════
    # RUN
    # ══════════════════════════════════════════════
    run_col1, run_col2 = st.columns([1, 3])
    with run_col1:
        run_btn = st.button("▶ Run all requests", type="primary", use_container_width=True)

    if run_btn:
        if not endpoint:
            st.error("Enter an endpoint URL.")
        else:
            # Parse headers
            try:
                req_headers = json.loads(headers_json) if headers_json.strip() else {}
            except:
                st.error("Invalid headers JSON.")
                st.stop()

            total = len(df)
            progress_bar = st.progress(0, text=f"Running 0/{total}...")
            status_area = st.empty()
            results_placeholder = st.empty()

            results = []
            ok_count = 0
            fail_count = 0

            # Results table header
            result_rows = []

            for i in range(total):
                row_data = df.iloc[i].to_dict()
                payload = build_row(row_data)

                try:
                    start = time.time()
                    if method in ["GET", "DELETE"]:
                        resp = requests.request(method, endpoint, headers=req_headers, timeout=30)
                    else:
                        resp = requests.request(method, endpoint, headers=req_headers, json=payload, timeout=30)

                    elapsed = round(time.time() - start, 2)
                    body = resp.text
                    code = resp.status_code
                    status = "✅" if 200 <= code < 300 else "❌"

                    if 200 <= code < 300:
                        ok_count += 1
                    else:
                        fail_count += 1

                except Exception as e:
                    elapsed = round(time.time() - start, 2) if 'start' in dir() else 0
                    status = "❌"
                    code = "ERR"
                    body = str(e)
                    fail_count += 1

                result_rows.append({
                    "Row": i + 1,
                    "Status": status,
                    "HTTP Code": code,
                    "Time (s)": elapsed,
                    "Request JSON": json.dumps(payload, default=str),
                    "Response": body[:300]
                })

                results.append({
                    "Row": i + 1,
                    "Status": "ok" if status == "✅" else "fail",
                    "HTTP Code": code,
                    "Time (s)": elapsed,
                    "Request JSON": json.dumps(payload, default=str),
                    "Full Response": body
                })

                # Update progress
                pct = (i + 1) / total
                progress_bar.progress(pct, text=f"Running {i+1}/{total}... ({ok_count} ✓ {fail_count} ✗)")

                # Update results table
                results_placeholder.dataframe(
                    pd.DataFrame(result_rows),
                    use_container_width=True,
                    height=min(400, 50 + len(result_rows) * 38)
                )

                if delay_ms > 0 and i < total - 1:
                    time.sleep(delay_ms / 1000)

            # Final stats
            progress_bar.progress(1.0, text="Done!")

            st.markdown("---")
            stat_cols = st.columns(3)
            with stat_cols[0]:
                st.markdown(f'<div class="metric-card"><h3>{ok_count}</h3><p>Success</p></div>', unsafe_allow_html=True)
            with stat_cols[1]:
                st.markdown(f'<div class="metric-card fail"><h3>{fail_count}</h3><p>Failed</p></div>', unsafe_allow_html=True)
            with stat_cols[2]:
                st.markdown(f'<div class="metric-card"><h3>{total}</h3><p>Total</p></div>', unsafe_allow_html=True)

            # Export CSV
            csv_buffer = io.StringIO()
            writer = csv.DictWriter(csv_buffer, fieldnames=["Row", "Status", "HTTP Code", "Time (s)", "Request JSON", "Full Response"])
            writer.writeheader()
            writer.writerows(results)

            st.download_button(
                label="📥 Download results CSV",
                data=csv_buffer.getvalue(),
                file_name=f"api-results-{time.strftime('%Y-%m-%d_%H%M%S')}.csv",
                mime="text/csv"
            )
