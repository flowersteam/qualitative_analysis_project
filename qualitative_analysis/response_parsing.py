# response_parsing.py
import json
import re


def parse_llm_response(evaluation_text, selected_fields):
    """
    Parses a language model's response to extract specified fields from a JSON object.

    This function searches for a JSON-formatted substring within the provided `evaluation_text`.
    If a JSON object is found, it parses the JSON and extracts the values corresponding to
    the `selected_fields`. If no JSON object is found or parsing fails, it returns a dictionary
    with `None` values for each selected field.

    This function is suitable for handling responses from applications like Streamlit
    where the language model is instructed to return responses in JSON format.

    Parameters:
        evaluation_text (str): The full text response from the language model.
        selected_fields (list): A list of field names (strings) to extract from the JSON object.

    Returns:
        dict: A dictionary where each key is a field from `selected_fields` and each value
              is the corresponding value from the JSON object or `None` if not found or parsing failed.

    Raises:
        ValueError: If no JSON object is found in the `evaluation_text`.

    Example:
        evaluation_text = '''
        Here is the evaluation of your entry:
        {
            "Evaluation": "Positive",
            "Comments": "Well-written and insightful."
        }
        Thank you!
        '''
        selected_fields = ['Evaluation', 'Comments']
        result = parse_llm_response(evaluation_text, selected_fields)
        # result => {'Evaluation': 'Positive', 'Comments': 'Well-written and insightful.'}
    """
    try:
        # Search for a JSON object within the evaluation_text
        json_text_match = re.search(r"\{.*\}", evaluation_text, re.DOTALL)
        if json_text_match:
            json_text = json_text_match.group(0)
            # Parse the JSON text
            evaluation_json = json.loads(json_text)
            # Extract the specified fields
            return {
                field: evaluation_json.get(field, None) for field in selected_fields
            }
        else:
            raise ValueError("No JSON object found in the LLM response.")
    except json.JSONDecodeError as e:
        # Handle JSON decoding errors
        print(f"JSON decoding error: {e}")
        return {field: None for field in selected_fields}
    except Exception as e:
        # Handle other exceptions
        print(f"Error parsing LLM response: {e}")
        return {field: None for field in selected_fields}


def extract_code_from_response(response_text, prefix=None):
    """
    Extracts an integer code from a language model response, optionally requiring a prefix.

    If 'prefix' is specified (e.g., "Validity:"), the function searches for a line matching:
        "<prefix> <digits>"
    case-insensitively, returning the integer. For example, "Validity: 1" -> 1

    If no 'prefix' is provided, it falls back to capturing the first integer in the text
    (e.g., "I think the code is 2" -> 2).

    Parameters:
        response_text (str): The text response from the language model.
        prefix (str, optional): A string that must precede the integer. Example: "Validity:" or "Score:".

    Returns:
        int or None: The extracted integer code if found, otherwise None.
    """
    if prefix:
        # Compile a regex pattern with the specified prefix
        # (?i) makes it case-insensitive
        # \b ensures word boundary before prefix
        # \s* matches any whitespace between prefix and colon
        # [:-]? matches an optional colon or hyphen
        # \s* matches any whitespace between colon/hyphen and digit
        # (\d+) captures one or more digits
        # \s*$ ensures that the digit is at the end of the line
        pattern = rf"(?i)\b{re.escape(prefix)}\s*[:\-]?\s*([+-]?\d+)\s*$"
        match = re.search(pattern, response_text, re.MULTILINE)
        if match:
            return int(match.group(1))
        else:
            return None
    else:
        # Capture the first integer in the text, including negatives
        number_search_result = re.search(r"[+-]?\d+", response_text)
        if number_search_result:
            return int(number_search_result.group())
        else:
            return None
