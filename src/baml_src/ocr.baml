enum ConfidenceLevel {
  LOW
  MED
  HIGH
}

class OcrPageResult {
  page_number int
  raw_text string
}

class FieldValue {
  value string?
  confidence ConfidenceLevel
}

class ListFieldValue {
  value string[]
  confidence ConfidenceLevel
}

class LandRecordFields {
  district FieldValue
  block FieldValue
  mouza FieldValue
  police_station FieldValue
  registry_location FieldValue
  plot_no FieldValue
  deed_no FieldValue
  registration_year FieldValue
  registration_month FieldValue
  registration_day FieldValue
  total_area FieldValue
  land_unit FieldValue
  vendors ListFieldValue
  vendees ListFieldValue
  deed_type FieldValue
}

function ExtractOcrBatch(page_images: image[]) -> OcrPageResult[] {
  client ClaudeClient
  prompt #"
    Transcribe each of the following document page images exactly as
    written, preserving mixed Bangla and English text. For each page,
    return its raw text.

    {{ ctx.output_format }}
  "#
}

function FillSchema(document_text: string) -> LandRecordFields {
  client ClaudeClient
  prompt #"
    Extract the following fixed set of fields from the land record
    document text below. For each field, return its value (or null/empty
    if not found) and a confidence level: LOW if the value is likely
    hallucinated or not actually present in the text, MED if plausible but
    uncertain, HIGH if clearly and directly stated.

    Fields to extract:
    - district, block, mouza, police_station, registry_location: location
      details of the land record.
    - plot_no: the plot number, whichever of LR/RS/CS plot number is
      present in the document.
    - deed_no: the deed number.
    - registration_year, registration_month, registration_day: the date
      the deed was registered, as separate values.
    - total_area: the total area of land transferred/given.
    - land_unit: the unit for total_area (e.g. decimal, acre, bigha, katha).
    - vendors: list of people transferring the land, with whatever info
      about each is extractable from the text.
    - vendees: list of people receiving the land, with whatever info about
      each is extractable from the text.
    - deed_type: the type of deed (e.g. gift, sale, partition).

    Document text:
    ---
    {{ document_text }}
    ---

    {{ ctx.output_format }}
  "#
}
