__author__ = "Vanessa Sochat"
__copyright__ = "Copyright 2016-2025, Vanessa Sochat"
__license__ = "MIT"

from pydicom.multival import MultiValue

from deid.logger import bot
from deid.utils import get_timestamp, parse_keyvalue_pairs

# Timestamps


def jitter_timestamp_func(item, value, field, **kwargs):
    """
    A wrapper to jitter_timestamp so it works as a custom function.
    """
    opts = parse_keyvalue_pairs(kwargs.get("extras"))

    # Default to jitter by one day
    value = int(opts.get("days", 1))

    # The user can optionally provide years
    if "years" in opts:
        value = (int(opts["years"]) * 365) + value
    return jitter_timestamp(field, value)


def jitter_timestamp(field, value):
    """
    Jitter a timestamp "field" by number of days specified by "value"

    The value can be positive or negative. This function is grandfathered
    into deid custom funcs, as it existed before they did. Since a custom
    func requires an item, we have a wrapper above to support this use case.

    Parameters
    ==========
    field: the field with the timestamp
    value: number of days to jitter by. Jitter bug!
    """
    if not isinstance(value, int):
        value = int(value)

    original = field.element.value
    new_value = original

    if original is not None:
        # Handle the case where we get a string representation of a list (common issue)
        if (
            isinstance(original, str)
            and original.startswith("[")
            and original.endswith("]")
        ):
            try:
                # Try to safely evaluate the string as a list
                import ast

                original = ast.literal_eval(original)
            except (ValueError, SyntaxError) as e:
                # If it fails, treat it as a single string value
                bot.warning(
                    f"Failed to parse string as list for field {field.name}: {e}. Treating as single value."
                )
                pass

        # Check if we have multiple values (MultiValue or list)
        is_multi_value = isinstance(original, (MultiValue, list))

        # Create default for new value
        new_value = None
        dcmvr = field.element.VR

        if is_multi_value:
            # Handle multiple values (like PET scans with multiple dates)
            bot.info(
                f"Processing {len(original)} dates for multi-value field {field.name}"
            )
            jittered_values = []
            for i, single_date in enumerate(original):
                single_jittered = None

                # DICOM Value Representation can be either DA (Date) DT (Timestamp),
                # or something else, which is not supported.
                try:
                    if dcmvr == "DA":
                        # NEMA-compliant format for DICOM date is YYYYMMDD
                        single_jittered = get_timestamp(
                            single_date, jitter_days=value, format="%Y%m%d"
                        )
                    elif dcmvr == "DT":
                        # NEMA-compliant format for DICOM timestamp is
                        # YYYYMMDDHHMMSS.FFFFFF&ZZXX
                        # Most DICOM timestamps don't include timezone, so try without timezone first
                        try:
                            single_jittered = get_timestamp(
                                single_date, jitter_days=value, format="%Y%m%d%H%M%S.%f"
                            )
                        except Exception as e:
                            bot.warning(
                                f"Failed with microseconds format for {single_date}: {e}"
                            )
                            try:
                                single_jittered = get_timestamp(
                                    single_date,
                                    jitter_days=value,
                                    format="%Y%m%d%H%M%S.%f%z",
                                )
                            except Exception as e2:
                                bot.warning(
                                    f"Failed with timezone format for {single_date}: {e2}"
                                )
                                # Try without microseconds
                                single_jittered = get_timestamp(
                                    single_date,
                                    jitter_days=value,
                                    format="%Y%m%d%H%M%S",
                                )
                    else:
                        # If the field type is not supplied, attempt to parse different formats
                        # Try more common formats first (no timezone, then with microseconds, then timezone)
                        for fmtstr in [
                            "%Y%m%d",
                            "%Y%m%d%H%M%S",
                            "%Y%m%d%H%M%S.%f",
                            "%Y%m%d%H%M%S.%f%z",
                        ]:
                            try:
                                single_jittered = get_timestamp(
                                    single_date, jitter_days=value, format=fmtstr
                                )
                                break
                            except Exception as e:
                                bot.warning(
                                    f"Failed to jitter {single_date} with format {fmtstr}: {e}"
                                )
                                pass
                except Exception as e:
                    bot.error(
                        f"Unexpected error jittering date {single_date} in field {field.name}: {e}"
                    )
                    single_jittered = None

                if single_jittered:
                    jittered_values.append(single_jittered)
                else:
                    bot.warning(
                        f"JITTER not supported for value '{single_date}' with VR={dcmvr} in field {field.name}"
                    )
                    jittered_values.append(
                        single_date
                    )  # Keep original if jittering fails

            # Return appropriate format for multi-value fields
            # Note: For multi-value DICOM fields, pydicom expects the same type as the original
            if isinstance(original, MultiValue):
                # For MultiValue fields, DICOM standard uses backslash-separated strings
                # This is the most compatible format across different pydicom versions
                new_value = "\\".join(str(v) for v in jittered_values)
                bot.debug(
                    f"Converted MultiValue to backslash-separated string: {new_value}"
                )
            else:
                # If original was a list but not MultiValue, try backslash-separated string
                new_value = "\\".join(str(v) for v in jittered_values)
                bot.debug(f"Converting list to backslash-separated string: {new_value}")

            bot.debug(
                f"Completed jittering {len(jittered_values)} dates for field {field.name}"
            )

            # For MultiValue fields, pydicom expects a list or sequence, not a MultiValue object
            # The DICOM library will automatically convert it to the appropriate type
        else:
            # Handle single value (existing behavior)
            try:
                # DICOM Value Representation can be either DA (Date) DT (Timestamp),
                # or something else, which is not supported.
                if dcmvr == "DA":
                    # NEMA-compliant format for DICOM date is YYYYMMDD
                    new_value = get_timestamp(
                        original, jitter_days=value, format="%Y%m%d"
                    )

                elif dcmvr == "DT":
                    # NEMA-compliant format for DICOM timestamp is
                    # YYYYMMDDHHMMSS.FFFFFF&ZZXX
                    # Most DICOM timestamps don't include timezone, so try without timezone first
                    try:
                        new_value = get_timestamp(
                            original, jitter_days=value, format="%Y%m%d%H%M%S.%f"
                        )
                    except Exception as e:
                        bot.warning(
                            f"Failed with microseconds format for {original}: {e}"
                        )
                        try:
                            new_value = get_timestamp(
                                original, jitter_days=value, format="%Y%m%d%H%M%S.%f%z"
                            )
                        except Exception as e2:
                            bot.warning(
                                f"Failed with timezone format for {original}: {e2}"
                            )
                            # Try without microseconds
                            new_value = get_timestamp(
                                original, jitter_days=value, format="%Y%m%d%H%M%S"
                            )

                else:
                    # If the field type is not supplied, attempt to parse different formats
                    # Try more common formats first (no timezone, then with microseconds, then timezone)
                    for fmtstr in [
                        "%Y%m%d",
                        "%Y%m%d%H%M%S",
                        "%Y%m%d%H%M%S.%f",
                        "%Y%m%d%H%M%S.%f%z",
                    ]:
                        try:
                            new_value = get_timestamp(
                                original, jitter_days=value, format=fmtstr
                            )
                            break
                        except Exception as e:
                            bot.warning(
                                f"Failed to jitter {original} with format {fmtstr}: {e}"
                            )
                            pass

            except Exception as e:
                bot.error(
                    f"Unexpected error jittering single value {original} in field {field.name}: {e}"
                )
                new_value = None

            # If nothing works for single values, issue a warning
            if not new_value:
                bot.warning(
                    f"JITTER not supported for field {field.name} with value '{original}' and VR={dcmvr}"
                )
    else:
        bot.debug(f"Field {field.name} has None/empty value, skipping jitter")

    bot.debug(
        f"Jitter returning value: {new_value} (type: {type(new_value)}) for field {field.name}"
    )
    return new_value
