// src/log_test/log_test.c
#include "postgres.h"
#include "fmgr.h"
#include "utils/builtins.h" // For text_to_cstring

// This macro is required for every PostgreSQL extension
PG_MODULE_MAGIC;

// Declare the C function that will be called from SQL
PG_FUNCTION_INFO_V1(pg_log_message);

Datum
pg_log_message(PG_FUNCTION_ARGS)
{
    // 1. Get the text argument passed from the SQL function call
    text *message_text = PG_GETARG_TEXT_P(0);

    // 2. Convert the PostgreSQL 'text' type into a standard C string
    char *message_cstring = text_to_cstring(message_text);

    // 3. Log the message to the server log at the INFO level
    elog(INFO, "pg_log_message: %s", message_cstring);

    // 4. Free the memory used by the C string
    pfree(message_cstring);

    // 5. SQL functions returning 'void' must return a NULL Datum
    PG_RETURN_NULL();
}