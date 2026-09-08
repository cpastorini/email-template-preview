from __future__ import annotations

import base64
import csv
import html
import io
import re
from dataclasses import dataclass

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Email Template Preview", page_icon="✉️", layout="wide")

REQUIRED_COLUMNS = {"COMM_SRV_ID", "SUBJECT", "FROM_ADDRESS", "XSL_TEMPLATE"}
VALUE_OF_RE = re.compile(r"<xsl:value-of\s+select=[\"']([^\"']+)[\"']\s*/?>", re.I)
ATTRIBUTE_BLOCK_RE = re.compile(r"<xsl:attribute\b[^>]*>.*?</xsl:attribute>", re.I | re.S)
XSL_TAG_RE = re.compile(r"</?xsl:[^>]+>", re.I)


@dataclass
class Templates:
    header: str
    footer: str
    base: str


def read_csv(uploaded_file) -> pd.DataFrame:
    data = uploaded_file.getvalue()
    last_error = None
    candidate_separators = [";", ",", "\t", "|"]

    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        separators = candidate_separators.copy()
        try:
            sample = data.decode(encoding, errors="ignore")[:10000]
            detected = csv.Sniffer().sniff(sample, delimiters=";,\t|").delimiter
            separators = [detected] + [sep for sep in candidate_separators if sep != detected]
        except Exception:
            pass

        for sep in separators:
            try:
                df = pd.read_csv(
                    io.BytesIO(data),
                    sep=sep,
                    quotechar='"',
                    encoding=encoding,
                    dtype=str,
                    keep_default_na=False,
                    engine="python",
                )
                if REQUIRED_COLUMNS.issubset(df.columns):
                    return df
            except Exception as exc:
                last_error = exc

        try:
            df = pd.read_csv(
                io.BytesIO(data),
                sep=None,
                quotechar='"',
                encoding=encoding,
                dtype=str,
                keep_default_na=False,
                engine="python",
            )
            if REQUIRED_COLUMNS.issubset(df.columns):
                return df
        except Exception as exc:
            last_error = exc

    raise ValueError(f"Unable to read the CSV: {last_error}")


def replace_placeholders(source: str, templates: Templates) -> str:
    """Resolve the email content first, then inject it into the base template.

    Supported patterns:
    1. XSL_TEMPLATE contains ${HEADER}/${FOOTER}: direct substitution.
    2. BASE_TEMPLATE contains ${TEMPLATE_CONTENT}: the resolved email content is inserted there.
    3. Legacy placeholders ${CONTENT} / ${EMAIL_CONTENT} are still supported.
    """
    source = source or ""

    email_content = source.replace("${HEADER}", templates.header).replace("${FOOTER}", templates.footer)

    if templates.base.strip():
        base_template = templates.base
        if "${TEMPLATE_CONTENT}" in base_template:
            return base_template.replace("${TEMPLATE_CONTENT}", email_content)
        if "${CONTENT}" in base_template:
            return base_template.replace("${CONTENT}", email_content)
        if "${EMAIL_CONTENT}" in base_template:
            return base_template.replace("${EMAIL_CONTENT}", email_content)

    return email_content


def preview_xsl_as_html(source: str, sample_values: dict[str, str]) -> str:
    """Return the resolved template verbatim for browser rendering.

    The preview should match the composed HTML as closely as possible, so we do not
    strip XSL tags or replace sample values here.
    """
    return source


def build_preview_data_uri(rendered_html: str, min_height: int) -> str:
        doc = f"""
<!doctype html>
<html>
<head>
    <meta charset=\"utf-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
    <style>
        html, body {{ margin: 0; padding: 0; background: #fff; }}
        .preview-wrap {{ min-height: {min_height}px; }}
    </style>
</head>
<body>
    <div class=\"preview-wrap\">{rendered_html}</div>
</body>
</html>
"""
        encoded = base64.b64encode(doc.encode("utf-8")).decode("ascii")
        return f"data:text/html;base64,{encoded}"


def find_xsl_fields(source: str) -> list[str]:
    return sorted({m.group(1).strip() for m in VALUE_OF_RE.finditer(source or "")})


def default_base_template() -> str:
    return """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="margin:0;background:#f5f5f5;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0">
    <tr><td align="center" style="padding:24px;">
      <table role="presentation" width="640" cellspacing="0" cellpadding="0" border="0" style="width:100%;max-width:640px;background:#ffffff;">
                ${TEMPLATE_CONTENT}
      </table>
    </td></tr>
  </table>
</body>
</html>"""


def build_export_csv(df: pd.DataFrame) -> bytes:
    edited_df = df.copy()
    for index, record in df.iterrows():
        row_id = record["COMM_SRV_ID"]
        edited_df.at[index, "SUBJECT"] = st.session_state.get(f"subject_{row_id}", record["SUBJECT"])
        edited_df.at[index, "FROM_ADDRESS"] = st.session_state.get(f"from_{row_id}", record["FROM_ADDRESS"])
        edited_df.at[index, "XSL_TEMPLATE"] = st.session_state.get(f"xsl_template_{row_id}", record["XSL_TEMPLATE"])

    return edited_df.to_csv(sep=";", index=False).encode("utf-8")


def read_uploaded_text(uploaded_file) -> str:
    data = uploaded_file.getvalue()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


st.title("✉️ Email XML / HTML Preview")
st.caption("CSV upload triggers an automatic render. Preview also updates when you edit template text fields.")

if "base_template" not in st.session_state:
    st.session_state["base_template"] = default_base_template()


def load_text_into_state(uploaded_file, state_key: str) -> None:
    if uploaded_file is not None:
        st.session_state[state_key] = read_uploaded_text(uploaded_file)


def stage_loaded_templates(header_file, footer_file, base_file) -> None:
    st.session_state["pending_template_load"] = {
        "header": read_uploaded_text(header_file),
        "footer": read_uploaded_text(footer_file),
        "base": read_uploaded_text(base_file),
    }

with st.sidebar:
    st.header("1. Email CSV")
    uploaded = st.file_uploader("Email CSV", type=["csv"], help="Expected separator: ';' with an XSL_TEMPLATE column.")
    st.divider()
    st.header("2. Base Template, Header, Footer")
    header_upload = st.file_uploader("Header file", type=["html", "xml", "txt"], key="header_upload")
    footer_upload = st.file_uploader("Footer file", type=["html", "xml", "txt"], key="footer_upload")
    base_upload = st.file_uploader("Base template file", type=["html", "xml", "txt"], key="base_upload")
    preview_height = 900

    render_clicked = st.button("Load and render email", key="load_all_templates")
    if render_clicked:
        required_uploads = {
            "Header file": header_upload,
            "Footer file": footer_upload,
            "Base template file": base_upload,
        }
        missing_uploads = [label for label, file in required_uploads.items() if file is None]
        if missing_uploads:
            st.warning("Upload all template files before loading: " + ", ".join(missing_uploads))
            render_clicked = False
        else:
            stage_loaded_templates(header_upload, footer_upload, base_upload)

csv_token = (getattr(uploaded, "name", ""), getattr(uploaded, "size", 0))
csv_just_loaded = st.session_state.get("last_csv_token") != csv_token
st.session_state["last_csv_token"] = csv_token

if uploaded is None:
    st.info("Upload a CSV to get started. The provided attachment format is already supported.")
    st.stop()

try:
    df = read_csv(uploaded)
except Exception as exc:
    st.error(str(exc))
    st.stop()

missing = REQUIRED_COLUMNS - set(df.columns)
if missing:
    st.error("Missing required columns: " + ", ".join(sorted(missing)))
    st.write("Columns found:", list(df.columns))
    st.stop()

selected_index = st.selectbox(
    "Email",
    options=df.index.tolist(),
    key="selected_email_index",
    format_func=lambda idx: f"{df.at[idx, 'COMM_SRV_ID']} · {st.session_state.get(f'subject_{df.at[idx, "COMM_SRV_ID"]}', df.at[idx, 'SUBJECT'])}",
)
row = df.loc[selected_index]
row_id = row["COMM_SRV_ID"]

pending_template_load = st.session_state.pop("pending_template_load", None)
if pending_template_load is not None:
    st.session_state["header_template"] = pending_template_load["header"]
    st.session_state["footer_template"] = pending_template_load["footer"]
    st.session_state["base_template"] = pending_template_load["base"]

meta1, meta2, meta3 = st.columns(3)
meta1.metric("COMM_SRV_ID", row["COMM_SRV_ID"])
subject = meta2.text_input("Subject", value=row["SUBJECT"], key=f"subject_{row_id}")
from_address = meta3.text_input("From", value=row["FROM_ADDRESS"], key=f"from_{row_id}")

st.subheader("Shared templates")
tab_header, tab_footer, tab_base = st.tabs(["${HEADER}", "${FOOTER}", "${BASE_TEMPLATE}"])
with tab_header:
    header_template = st.text_area("Header HTML/XML", height=190, key="header_template", placeholder="Paste the shared header here...")
with tab_footer:
    footer_template = st.text_area("Footer HTML/XML", height=190, key="footer_template", placeholder="Paste the shared footer here...")
with tab_base:
    base_template = st.text_area(
        "Base template HTML",
        height=260,
        key="base_template",
        help="Use ${TEMPLATE_CONTENT} as the email insertion point. Legacy ${CONTENT} and ${EMAIL_CONTENT} placeholders are also supported.",
    )

templates = Templates(header_template, footer_template, base_template)
source_template = st.text_area(
    "Email HTML/XSL",
    value=row["XSL_TEMPLATE"],
    height=220,
    key=f"xsl_template_{row_id}",
    help="Edit the source template for the selected email. The preview and export use this value.",
)
st.download_button(
    "Save email",
    data=source_template.encode("utf-8"),
    file_name=f"email_{row['COMM_SRV_ID']}_template.html",
    mime="text/html",
    use_container_width=True,
)

current_render_inputs = {
    "row_id": row_id,
    "source": source_template,
    "header": header_template,
    "footer": footer_template,
    "base": base_template,
}
text_fields_changed = st.session_state.get("last_render_inputs") != current_render_inputs

render_requested = csv_just_loaded or render_clicked or text_fields_changed
if render_requested:
    resolved_snapshot = replace_placeholders(source_template, templates)
    rendered_snapshot = preview_xsl_as_html(resolved_snapshot, {})
    st.session_state["resolved_snapshot"] = resolved_snapshot
    st.session_state["rendered_snapshot"] = rendered_snapshot
    st.session_state["rendered_row_id"] = row_id
    st.session_state["last_render_inputs"] = current_render_inputs

resolved = st.session_state.get("resolved_snapshot", "")
rendered = st.session_state.get("rendered_snapshot", "")
rendered_for_selected_row = st.session_state.get("rendered_row_id") == row_id and bool(rendered)

download_col1, download_col2 = st.columns(2)
with download_col1:
    st.download_button(
        "Download resolved HTML",
        data=rendered.encode("utf-8") if rendered_for_selected_row else b"",
        file_name=f"email_{row['COMM_SRV_ID']}_preview.html",
        mime="text/html",
        disabled=not rendered_for_selected_row,
        use_container_width=True,
    )

with download_col2:
    st.download_button(
        "Download edited CSV",
        data=build_export_csv(df),
        file_name="email_templates_edited.csv",
        mime="text/csv",
        use_container_width=True,
    )

st.subheader("Preview")
if rendered_for_selected_row:
    preview_src = build_preview_data_uri(rendered, preview_height - 20)
    st.iframe(preview_src, height=preview_height)
else:
    st.info("Click 'Load and render email' to update the preview for the selected email.")

if rendered_for_selected_row:
    unresolved = [p for p in ("${HEADER}", "${FOOTER}", "${TEMPLATE_CONTENT}", "${CONTENT}", "${EMAIL_CONTENT}") if p in resolved]
    if unresolved:
        st.warning("Placeholders still present: " + ", ".join(unresolved))
    else:
        st.success("Shared placeholders resolved.")

st.subheader("Source")
source_tab, resolved_tab, rendered_tab = st.tabs(["CSV", "Resolved", "Preview HTML"])
with source_tab:
    st.code(source_template, language="xml")
with resolved_tab:
    st.code(resolved if rendered_for_selected_row else "", language="xml")
with rendered_tab:
    st.code(rendered if rendered_for_selected_row else "", language="html")
