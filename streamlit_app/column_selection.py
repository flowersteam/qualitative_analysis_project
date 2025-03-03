"""
Module for handling column selection, renaming, and description functionality in the Streamlit app.
"""

import streamlit as st
import pandas as pd
from typing import Dict, List, Optional, Any

from qualitative_analysis import clean_and_normalize, sanitize_dataframe


def select_rename_describe_columns(
    app_instance: Any, data: pd.DataFrame
) -> Optional[pd.DataFrame]:
    """
    Step 2:
    1) Lets the user select which columns contain existing human annotations.
    2) Subsets the dataframe to rows that have non-NA in those annotation columns (if any).
    3) Lets the user select which columns to include for LLM analysis (excluding annotation columns).
    4) Lets user rename and describe those selected columns.
    5) Cleans and normalizes text columns.

    Args:
        app_instance: The QualitativeAnalysisApp instance
        data: The DataFrame to process

    Returns:
        The processed DataFrame or None if no data was provided
    """
    st.header("Step 2: Column Selections (Annotation Columns + Data Columns)")

    if data is None:
        st.error("No dataset loaded.")
        return None

    columns = data.columns.tolist()

    # 2.1: Let user pick the annotation columns
    st.markdown(
        """
        Select column(s) that contain *human annotations*.
        Rows missing those annotations will be filtered out
        so that the dataset in the first part of the analysis only includes fully annotated entries.
        """,
        unsafe_allow_html=True,
    )

    app_instance.annotation_columns = st.multiselect(
        "Annotation Column(s):",
        options=columns,
        default=st.session_state.get("annotation_columns", []),
        key="annotation_columns_selection",
    )

    # Filter to keep only rows that have non-NA in these annotation columns
    if app_instance.annotation_columns:
        data = data.dropna(subset=app_instance.annotation_columns)
        st.write(
            f"**Filtered** dataset to remove rows without annotations in {app_instance.annotation_columns}."
        )
        st.write(f"New dataset size: {data.shape[0]} rows.")

        # If annotation columns are selected, ask for the expected data type
        st.subheader("Label Type Configuration")
        st.markdown(
            """
            Select the expected data type for your labels (both human annotations and LLM predictions).
            This helps ensure consistent data types for evaluation.
            """
        )

        # Select the expected data type for the labels
        label_type = st.radio(
            "Expected Label Type:",
            options=["Integer", "Float", "Text (str)"],
            index=0,
            key="label_type_radio",
        )

        # Store in session state
        st.session_state["label_type"] = label_type

    # Store final annotation columns in session
    st.session_state["annotation_columns"] = app_instance.annotation_columns

    # 2.2: Select the columns that will be analyzed (exclude annotation columns)
    columns_for_analysis = [
        c for c in data.columns if c not in app_instance.annotation_columns
    ]

    st.markdown(
        """
        Now, select the *analysis columns* (the columns you want the LLM to process).
        You should generally *exclude* your annotation columns here.
        """,
        unsafe_allow_html=True,
    )

    previous_selection = st.session_state.get("selected_columns", [])
    # Filter out invalid columns
    valid_previous_selection = [
        col for col in previous_selection if col in columns_for_analysis
    ]

    app_instance.selected_columns = st.multiselect(
        "Columns to analyze:",
        options=columns_for_analysis,
        default=(
            valid_previous_selection
            if valid_previous_selection
            else columns_for_analysis
        ),
    )
    st.session_state["selected_columns"] = app_instance.selected_columns

    if not app_instance.selected_columns:
        st.info("Select at least one column to proceed.")
        return None

    # 2.3: Rename columns
    for col in app_instance.selected_columns:
        default_rename = app_instance.column_renames.get(col, col)
        new_name = st.text_input(
            f"Rename '{col}' to:", value=default_rename, key=f"rename_{col}"
        )
        app_instance.column_renames[col] = new_name
    st.session_state["column_renames"] = app_instance.column_renames

    # 2.4: Descriptions
    st.write("Add a short description for each selected column:")
    for col in app_instance.selected_columns:
        renamed_col = app_instance.column_renames[col]
        default_desc = app_instance.column_descriptions.get(renamed_col, "")
        desc = st.text_area(
            f"Description for '{renamed_col}':",
            height=70,
            value=default_desc,
            key=f"desc_{renamed_col}",
        )
        app_instance.column_descriptions[renamed_col] = desc
    st.session_state["column_descriptions"] = app_instance.column_descriptions

    # 2.5: Cleaning & Normalizing text columns
    st.markdown(
        """ 
        Select which columns (among your selected ones) contain textual data to be cleaned & normalized.
        """,
        unsafe_allow_html=True,
    )

    # Build a DataFrame with only the selected columns (renamed)
    processed = data[app_instance.selected_columns].rename(
        columns=app_instance.column_renames
    )

    text_cols: List[str] = st.multiselect(
        "Text columns:",
        processed.columns.tolist(),
        default=processed.columns.tolist(),
        key="text_columns_selection",
    )

    # Clean and sanitize
    for tcol in text_cols:
        processed[tcol] = clean_and_normalize(processed[tcol])
    processed = sanitize_dataframe(processed)

    # Keep the annotation columns in the processed data, so we can do Step 7 easily
    for ann_col in app_instance.annotation_columns:
        if ann_col not in processed.columns:
            processed[ann_col] = data[ann_col]

    # Store processed data
    app_instance.processed_data = processed
    st.session_state["processed_data"] = processed

    # Rebuild column_descriptions so it only includes the newly renamed analysis columns
    updated_column_descriptions: Dict[str, str] = {}
    for col in processed.columns:
        if col in app_instance.column_renames.values():
            updated_column_descriptions[col] = app_instance.column_descriptions.get(
                col, ""
            )
    app_instance.column_descriptions = updated_column_descriptions
    st.session_state["column_descriptions"] = app_instance.column_descriptions

    st.success("Columns processed successfully!")
    st.write("Processed Data Preview:")
    st.dataframe(processed.head())

    return processed
