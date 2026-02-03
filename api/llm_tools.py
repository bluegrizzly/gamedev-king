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
                    },
                    "required": ["input_filename", "format"],
                },
            },
        },
    ]
