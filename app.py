# app.py

import streamlit as st
import pandas as pd

from qualitative_analysis.data_processing import (
    load_data, clean_and_normalize, sanitize_dataframe
)
from qualitative_analysis.prompt_construction import (
    build_data_format_description, construct_prompt
)
from qualitative_analysis.model_interaction import get_llm_client
from qualitative_analysis.response_parsing import parse_llm_response
from qualitative_analysis.utils import save_results_to_csv
from qualitative_analysis.evaluation import compute_cohens_kappa
from qualitative_analysis.cost_estimation import openai_api_calculate_cost
import qualitative_analysis.config as config

class QualitativeAnalysisApp:
    def __init__(self):
        # Initialize from session_state or default
        self.data = st.session_state.get('data', None)
        self.processed_data = st.session_state.get('processed_data', None)
        
        self.selected_columns = st.session_state.get('selected_columns', [])
        self.column_renames = st.session_state.get('column_renames', {})
        self.column_descriptions = st.session_state.get('column_descriptions', {})
        
        self.codebook = st.session_state.get('codebook', "")
        self.examples = st.session_state.get('examples', "")
        
        self.llm_client = None  # will instantiate later
        self.selected_model = st.session_state.get('selected_model', None)
        
        self.selected_fields = st.session_state.get('selected_fields', [])
        self.results = st.session_state.get('results', [])

    def run(self):
        st.title("Qualitative Analysis")

        # Step 1: Upload Dataset
        self.upload_dataset()

        # Steps 2-4 are only relevant if data is uploaded
        if self.data is not None:
            # Step 2: Select & Rename Columns, Add Descriptions
            self.select_rename_describe_columns()

            # Step 3: Codebook & Examples
            self.codebook_and_examples()

            # Step 4: Fields to Extract
            self.select_fields()

            # Step 5: Configure LLM (provider & model)
            self.configure_llm()

            # Step 6: Run Analysis
            self.run_analysis()

            # Step 7: Compare with External Judgments (Optional)
            self.compare_with_external_judgments()

    def upload_dataset(self):
        st.header("Step 1: Upload Your Dataset")
        uploaded_file = st.file_uploader("Upload CSV or XLSX", type=["csv", "xlsx"])
        
        if uploaded_file is not None:
            file_type = "csv" if uploaded_file.name.endswith(".csv") else "xlsx"
            delimiter = st.text_input("CSV Delimiter (if CSV)", value=";")

            try:
                data = load_data(uploaded_file, file_type=file_type, delimiter=delimiter)
                st.success("Data loaded successfully!")
                st.write("Data Preview:", data.head())

                # Store in session_state + local attribute
                self.data = data
                st.session_state['data'] = data

            except Exception as e:
                st.error(f"Error loading data: {e}")
                st.stop()

    def select_rename_describe_columns(self):
        st.header("Step 2: Select, Rename, and Describe Columns")
        
        if self.data is None:
            st.error("No dataset loaded.")
            return
        
        columns = self.data.columns.tolist()

        st.write("Select which columns to include in your analysis:")
        self.selected_columns = st.multiselect(
            "Columns to include:",
            columns,
            default=self.selected_columns if self.selected_columns else columns
        )
        st.session_state['selected_columns'] = self.selected_columns

        if not self.selected_columns:
            st.info("Select at least one column to proceed.")
            return
        
        # Rename columns
        for col in self.selected_columns:
            default_rename = self.column_renames.get(col, col)
            new_name = st.text_input(f"Rename '{col}' to:", value=default_rename)
            self.column_renames[col] = new_name
        st.session_state['column_renames'] = self.column_renames
        
        # Descriptions
        st.write("Add a short description for each selected column:")
        for col in self.selected_columns:
            col_key = self.column_renames[col]
            default_desc = self.column_descriptions.get(col_key, "")
            desc = st.text_area(f"Description for '{col_key}':", height=70, value=default_desc)
            self.column_descriptions[col_key] = desc
        st.session_state['column_descriptions'] = self.column_descriptions

        # Process & sanitize
        if self.selected_columns:
            processed = self.data[self.selected_columns].rename(columns=self.column_renames)
            
            st.write("Which columns do you want to clean & normalize?")
            text_cols = st.multiselect("Text columns:", processed.columns.tolist(), default=processed.columns.tolist())

            for tcol in text_cols:
                processed[tcol] = clean_and_normalize(processed[tcol])
            processed = sanitize_dataframe(processed)
            
            self.processed_data = processed
            st.session_state['processed_data'] = processed

            st.success("Columns processed successfully!")
            st.write("Processed Data Preview:")
            st.dataframe(self.processed_data.head())

    def codebook_and_examples(self):
        st.header("Step 3: Codebook & Examples")
        default_codebook = st.session_state.get('codebook', "")
        default_examples = st.session_state.get('examples', "")
        
        codebook_val = st.text_area("Codebook / Instructions for LLM:", value=default_codebook)
        examples_val = st.text_area("Examples (Optional):", value=default_examples)
        
        self.codebook = codebook_val
        self.examples = examples_val

        st.session_state['codebook'] = codebook_val
        st.session_state['examples'] = examples_val

    def select_fields(self):
        st.header("Step 4: Fields to Extract")
        default_fields = ",".join(self.selected_fields) if self.selected_fields else ""
        fields_str = st.text_input("Comma-separated fields (e.g. 'Evaluation, Comments')", value=default_fields)
        extracted = [f.strip() for f in fields_str.split(",") if f.strip()]
        
        self.selected_fields = extracted
        st.session_state['selected_fields'] = extracted

    def configure_llm(self):
        st.header("Step 5: Choose the Model")
        
        provider_options = ['OpenAI', 'Together']
        # We'll see if there's a previous provider stored in session_state. But for simplicity, we always ask the user again:
        selected_provider_display = st.selectbox("Select LLM Provider:", provider_options)

        provider_map = {
            "OpenAI": "azure",
            "Together": "together"
        }
        internal_provider = provider_map[selected_provider_display]

        if internal_provider not in config.MODEL_CONFIG:
            st.error(f"Missing configuration for provider: {internal_provider}")
            return

        if selected_provider_display == 'OpenAI':
            model_options = ["gpt-4o", "gpt-4o-mini"]
        else:
            model_options = ["together/gpt-neoxt-chat-20B"]

        default_model = self.selected_model if self.selected_model in model_options else model_options[0]
        chosen_model = st.selectbox("Select Model:", model_options, index=model_options.index(default_model) if default_model in model_options else 0)

        self.selected_model = chosen_model
        st.session_state['selected_model'] = chosen_model

        self.llm_client = get_llm_client(
            provider=internal_provider,
            config=config.MODEL_CONFIG[internal_provider]
        )

    def run_analysis(self):
        st.header("Step 6: Run Analysis")
        
        if self.processed_data is None or self.processed_data.empty:
            st.warning("No processed data. Please go to Step 2.")
            return

        if not self.codebook.strip():
            st.warning("Please provide a codebook in Step 3.")
            return

        if not self.selected_fields:
            st.warning("Please specify the fields to extract in Step 4.")
            return

        if not self.llm_client or not self.selected_model:
            st.warning("Please configure the model in Step 5.")
            return

        # Allow selecting a subset of rows
        st.subheader("Choose how many rows to analyze")
        process_options = ["All rows", "Subset of rows"]
        selected_option = st.radio("Process:", process_options, index=0)

        num_rows = len(self.processed_data)
        if selected_option == "Subset of rows":
            num_rows = st.number_input(
                "Number of rows to process:",
                min_value=1,
                max_value=len(self.processed_data),
                value=min(10, len(self.processed_data)),
                step=1
            )

        # Cost Estimation for the First Entry
        st.subheader("Cost Estimation")
        if st.button("Estimate Cost for First Entry"):
            first_entry = self.processed_data.iloc[0]
            entry_text_str = "\n".join([f"{col}: {first_entry[col]}" for col in self.processed_data.columns])

            # Build Prompt
            data_format_description = build_data_format_description(self.column_descriptions)
            prompt = construct_prompt(
                data_format_description=data_format_description,
                entry_text=entry_text_str,
                codebook=self.codebook,
                examples=self.examples,
                instructions="You are an assistant that evaluates data entries.",
                selected_fields=self.selected_fields,
                output_format_example={field: "Sample text" for field in self.selected_fields}
            )

            # Get token usage and calculate cost
            try:
                response, usage = self.llm_client.get_response(
                    prompt=prompt,
                    model=self.selected_model,
                    max_tokens=500,
                    temperature=0
                )
                cost_for_one = openai_api_calculate_cost(usage, self.selected_model)
                total_cost_estimate = cost_for_one * num_rows

                st.info(f"Estimated cost for processing one entry: ${cost_for_one:.4f}")
                st.info(f"Estimated total cost for {num_rows} entries: ${total_cost_estimate:.4f}")
            except Exception as e:
                st.error(f"Error estimating cost: {e}")


        # User Confirmation
        proceed = st.checkbox("I confirm to proceed with the analysis based on the estimated cost.")
        if not proceed:
            st.warning("Analysis aborted.")
            return

        # Start Full Analysis
        if st.button("Run Analysis"):
            st.info("Processing entries...")
            results = []
            progress_bar = st.progress(0)

            data_to_process = self.processed_data.head(num_rows)
            total = len(data_to_process)

            for i, (idx, row) in enumerate(data_to_process.iterrows()):
                entry_text_str = "\n".join([f"{col}: {row[col]}" for col in data_to_process.columns])

                prompt = construct_prompt(
                    data_format_description=data_format_description,
                    entry_text=entry_text_str,
                    codebook=self.codebook,
                    examples=self.examples,
                    instructions="You are an assistant that evaluates data entries.",
                    selected_fields=self.selected_fields,
                    output_format_example={field: "Your text here" for field in self.selected_fields}
                )

                try:
                    response = self.llm_client.get_response(
                        prompt=prompt,
                        model=self.selected_model,
                        max_tokens=500,
                        temperature=0,
                        verbose=False
                    )
                    parsed = parse_llm_response(response, self.selected_fields)
                    results.append({**row.to_dict(), **parsed})
                except Exception as e:
                    st.error(f"Error processing row {idx}: {e}")
                    continue

                progress_bar.progress((i + 1) / total)

            self.results = results
            st.session_state['results'] = results

            st.success("Analysis completed!")
            results_df = pd.DataFrame(results)
            st.dataframe(results_df)

            st.header("Save Results")
            filename = st.text_input("Filename", value="results.csv")
            if st.button("Save to CSV"):
                save_results_to_csv(
                    coding=results,
                    save_path=filename,
                    fieldnames=list(results_df.columns),
                    verbatims=None
                )
                st.success(f"Results saved to {filename}")

    def compare_with_external_judgments(self):
        st.header("Step 7: Compare with External Judgments (Optional)")
        comparison_file = st.file_uploader("Upload a comparison dataset (CSV or XLSX)", type=["csv", "xlsx"])

        if comparison_file is not None:
            file_type = "csv" if comparison_file.name.endswith(".csv") else "xlsx"
            try:
                comp_data = load_data(comparison_file, file_type=file_type, delimiter=';')
                st.write("Comparison data preview:")
                st.dataframe(comp_data.head())

                # Retrieve results from session_state if needed
                if not self.results:
                    self.results = st.session_state.get('results', [])
                if not self.results:
                    st.error("No analysis results found. Please run the analysis first.")
                    return

                results_df = pd.DataFrame(self.results)

                # Let user pick the key columns from each DataFrame
                llm_columns = results_df.columns.tolist()
                comp_columns = comp_data.columns.tolist()

                st.subheader("Select key column to merge on (LLM Results)")
                llm_key_col = st.selectbox("LLM Key Column:", llm_columns)

                st.subheader("Select key column to merge on (Comparison Dataset)")
                comp_key_col = st.selectbox("Comparison Key Column:", comp_columns)

                # Convert both sides to string or int (string is often safer)
                results_df[llm_key_col] = results_df[llm_key_col].astype(str)
                comp_data[comp_key_col] = comp_data[comp_key_col].astype(str)

                # Perform the merge
                merged = pd.merge(
                    results_df,
                    comp_data,
                    left_on=llm_key_col,
                    right_on=comp_key_col,
                    how="inner"
                )

                st.write("Merged Dataframe:")
                st.dataframe(merged.head())

                st.subheader("Select columns to compute Cohen's Kappa:")
                merged_columns = merged.columns.tolist()
                llm_judgment_col = st.selectbox("LLM Judgment Column:", merged_columns)
                external_judgment_col = st.selectbox("External Judgment Column:", merged_columns)

                if st.button("Compute Cohen's Kappa"):
                    if llm_judgment_col not in merged.columns or external_judgment_col not in merged.columns:
                        st.error("Selected columns not found in merged data.")
                        return

                    # Drop NaNs first
                    judgments_1 = merged[llm_judgment_col].dropna()
                    judgments_2 = merged[external_judgment_col].dropna()

                    # Convert both to int, or keep them as string and label-encode if needed
                    try:
                        judgments_1 = judgments_1.astype(int)
                        judgments_2 = judgments_2.astype(int)
                    except ValueError:
                        st.error(f"Could not convert {llm_judgment_col} or {external_judgment_col} to int. Ensure they contain valid integers.")
                        return

                    if len(judgments_1) == 0 or len(judgments_2) == 0:
                        st.error("No valid data to compare after converting to int.")
                        return

                    kappa = compute_cohens_kappa(judgments_1, judgments_2)
                    st.write(f"Cohen's Kappa: {kappa:.4f}")

            except Exception as e:
                st.error(f"Error loading comparison file: {e}")


def main():
    app = QualitativeAnalysisApp()
    app.run()

if __name__ == "__main__":
    main()
