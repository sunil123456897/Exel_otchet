import sys

path = 'APP/core/infra/ingestion_reader.py'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

old_pass1 = '''                try:
                    rows_sample = []
                    for idx, row in enumerate(sheet.iter_rows()):
                        rows_sample.append(row)
                        if idx >= MAX_HEADER_SCAN_ROWS - 1:
                            break
                except BaseException as iter_err:
                    if isinstance(iter_err, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                        raise
                    if iter_err.__class__.__name__ != "PanicException":
                        raise
                    # python-calamine can panic on some empty/broken sheets when iterating.
                    # Fallback to to_python() only for this edge case.
                    logger.debug(
                        f"iter_rows failed for sheet {sheet_name} with {type(iter_err).__name__}: {iter_err}. "
                        f"Falling back to to_python()."
                    )
                    try:
                        rows_sample = sheet.to_python()[:MAX_HEADER_SCAN_ROWS]
                    except Exception as e:
                        logger.debug(f"Could not read sheet {sheet_name}: {e}")
                        continue
                except Exception as e:
                    logger.debug(f"Could not read sheet {sheet_name}: {e}")
                    continue'''

new_pass1 = '''                use_to_python = False
                try:
                    rows_sample = []
                    for idx, row in enumerate(sheet.iter_rows()):
                        rows_sample.append(row)
                        if idx >= MAX_HEADER_SCAN_ROWS - 1:
                            break
                except BaseException as iter_err:
                    if isinstance(iter_err, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                        raise
                    logger.debug(
                        f"iter_rows failed for sheet {sheet_name} with {type(iter_err).__name__}: {iter_err}. "
                        f"Falling back to to_python()."
                    )
                    use_to_python = True
                    try:
                        rows_sample = sheet.to_python()[:MAX_HEADER_SCAN_ROWS]
                    except Exception as e:
                        logger.debug(f"Could not read sheet {sheet_name}: {e}")
                        continue'''

if old_pass1 not in content:
    print('old_pass1 not found')
else:
    content = content.replace(old_pass1, new_pass1)


old_pass2 = '''                for i, row in enumerate(sheet.iter_rows()):'''

new_pass2 = '''                row_iterator = enumerate(sheet.to_python() if use_to_python else sheet.iter_rows())
                while True:
                    try:
                        i, row = next(row_iterator)
                    except StopIteration:
                        break
                    except BaseException as second_pass_err:
                        if isinstance(second_pass_err, (KeyboardInterrupt, SystemExit, GeneratorExit)):
                            raise
                        logger.warning(f"Error during second pass in sheet {sheet_name}: {type(second_pass_err).__name__} - {second_pass_err}")
                        break'''

if old_pass2 not in content:
    print('old_pass2 not found')
else:
    content = content.replace(old_pass2, new_pass2)

with open(path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Replaced successfully")
