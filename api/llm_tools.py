def get_tools() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "export_pdf",
                "description": (
                    "Save a generated document to a PDF file on disk. "
                    "Use only when the user explicitly asks to save or export to PDF."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title to display in the PDF."},
                        "content": {
                            "type": "string",
                            "description": "Full document content to write into the PDF.",
                        },
                        "filename": {
                            "type": "string",
                            "description": "Optional filename for the PDF (e.g. report.pdf).",
                        },
                    },
                    "required": ["title", "content"],
                },
            },
        }
    ]
