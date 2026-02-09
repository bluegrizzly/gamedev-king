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
                        "project_key": {
                            "type": "string",
                            "description": "Optional project key to choose output directory.",
                        },
                    },
                    "required": ["title", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "export_docx",
                "description": (
                    "Save a generated document to a DOCX file on disk. "
                    "Use only when the user explicitly asks to save or export to DOCX."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title to display in the DOCX."},
                        "content": {
                            "type": "string",
                            "description": "Full document content to write into the DOCX.",
                        },
                        "filename": {
                            "type": "string",
                            "description": "Optional filename for the DOCX (e.g. report.docx).",
                        },
                        "project_key": {
                            "type": "string",
                            "description": "Optional project key to choose output directory.",
                        },
                    },
                    "required": ["title", "content"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "generate_image",
                "description": "Generate a new image from a text prompt.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "prompt": {"type": "string", "description": "Text prompt for the image."},
                        "negative_prompt": {
                            "type": "string",
                            "description": "Optional negative prompt to avoid elements.",
                        },
                        "width": {"type": "integer", "description": "Width in pixels (512/768/1024)."},
                        "height": {"type": "integer", "description": "Height in pixels (512/768/1024)."},
                        "num_images": {"type": "integer", "description": "Number of images to generate (1-4)."},
                        "seed": {"type": "integer", "description": "Optional seed for reproducibility."},
                        "model": {"type": "string", "description": "Optional model identifier."},
                        "project_key": {
                            "type": "string",
                            "description": "Optional project key to choose output directory.",
                        },
                    },
                    "required": ["prompt"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "resize_image",
                "description": "Resize an existing image by filename.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input_filename": {"type": "string", "description": "Existing image filename."},
                        "width": {"type": "integer", "description": "Target width in pixels."},
                        "height": {"type": "integer", "description": "Target height in pixels."},
                        "mode": {
                            "type": "string",
                            "description": "Resize mode: contain, cover, or stretch.",
                        },
                        "output_filename": {
                            "type": "string",
                            "description": "Optional output filename.",
                        },
                        "project_key": {
                            "type": "string",
                            "description": "Optional project key to choose output directory.",
                        },
                    },
                    "required": ["input_filename", "width", "height"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "crop_image",
                "description": "Crop an existing image by filename and rectangle.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input_filename": {"type": "string", "description": "Existing image filename."},
                        "x": {"type": "integer", "description": "X coordinate of crop origin."},
                        "y": {"type": "integer", "description": "Y coordinate of crop origin."},
                        "width": {"type": "integer", "description": "Crop width."},
                        "height": {"type": "integer", "description": "Crop height."},
                        "output_filename": {
                            "type": "string",
                            "description": "Optional output filename.",
                        },
                        "project_key": {
                            "type": "string",
                            "description": "Optional project key to choose output directory.",
                        },
                    },
                    "required": ["input_filename", "x", "y", "width", "height"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "convert_image",
                "description": "Convert an image to another format.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input_filename": {"type": "string", "description": "Existing image filename."},
                        "format": {"type": "string", "description": "png, jpg, or webp."},
                        "quality": {"type": "integer", "description": "Optional quality for jpg/webp."},
                        "output_filename": {
                            "type": "string",
                            "description": "Optional output filename.",
                        },
                        "project_key": {
                            "type": "string",
                            "description": "Optional project key to choose output directory.",
                        },
                    },
                    "required": ["input_filename", "format"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "export_xlsx",
                "description": (
                    "Save a spreadsheet workbook to an .xlsx file in the current project's gen folder. "
                    "Use when the user asks to create, save, or export a spreadsheet (xlsx, Excel). "
                    "Provide sheets as a list of { name: string, rows: string[][] }."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string", "description": "Title of the workbook."},
                        "sheets": {
                            "type": "array",
                            "description": "List of sheets. Each: { name: string, rows: array of array of cell values (string or number) }.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "name": {"type": "string", "description": "Sheet name."},
                                    "rows": {
                                        "type": "array",
                                        "description": "Rows of cells; each row is an array of values.",
                                        "items": {"type": "array", "items": {}},
                                    },
                                },
                                "required": ["name", "rows"],
                            },
                        },
                        "filename": {
                            "type": "string",
                            "description": "Optional filename (e.g. report.xlsx).",
                        },
                        "project_key": {
                            "type": "string",
                            "description": "Optional project key; uses current project if omitted.",
                        },
                    },
                    "required": ["title", "sheets"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "load_skill",
                "description": (
                    "Load the full instructions for an available skill. "
                    "Call this when the user's task matches a skill listed in <available_skills> so you can follow that skill's guidelines."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "skill_name": {
                            "type": "string",
                            "description": "Name of the skill (e.g. xlsx). Must match a skill from <available_skills>.",
                        },
                    },
                    "required": ["skill_name"],
                },
            },
        },
    ]
