class OcrPageResult {
  page_number int
  raw_text string
}

class SchemaField {
  field_name string
  value string?
  confidence float
}

function ExtractOcrBatch(page_images: image[]) -> OcrPageResult[] {
  client DefaultClient
  prompt #"
    Transcribe each of the following document page images exactly as
    written, preserving mixed Bangla and English text. For each page,
    return its raw text.

    {{ ctx.output_format }}
  "#
}

function FillSchema(document_text: string) -> SchemaField[] {
  client DefaultClient
  prompt #"
    Extract the fixed set of schema fields from the following document
    text. For each field, return its value (or null if not found) and a
    confidence score between 0 and 1.

    Document text:
    ---
    {{ document_text }}
    ---

    {{ ctx.output_format }}
  "#
}
