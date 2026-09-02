# Email Template Preview - Streamlit + uv

Streamlit app to preview HTML/XSL emails from a CSV such as `email_fr.csv` in real time.

## Features

- CSV upload with `;` as separator and quoted multiline fields;
- email selection via `COMM_SRV_ID` and `SUBJECT`;
- separate inputs for `${HEADER}`, `${FOOTER}`, and `${BASE_TEMPLATE}`;
- support for `${CONTENT}` / `${EMAIL_CONTENT}` inside the base template;
- editable `SUBJECT`, `FROM_ADDRESS`, and `XSL_TEMPLATE` for the selected row;
- Desktop/Mobile preview;
- visual replacement of `<xsl:value-of select="..."/>` with editable sample data;
- original source, resolved template, and preview HTML source views;
- download of the resulting HTML and an edited CSV copy.

> Note: the app does not run a full XSLT processor, so it does not evaluate `xsl:choose`, `xsl:when`, and similar constructs. For browser preview it removes XSL control tags and keeps the resulting HTML. If you need real XSLT evaluation, you must also provide sample XML data and the complete XSLT structure.

## Run with uv

```bash
uv sync
uv run streamlit run app.py
```

Then open the address shown by Streamlit, usually `http://localhost:8501`.

## Expected CSV

The minimum required columns are:

```text
COMM_SRV_ID;SUBJECT;FROM_ADDRESS;XSL_TEMPLATE
```
