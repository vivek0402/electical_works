# The client works in DD-MM-YYYY. Overrides Django's built-in "en" locale formats.
DATE_FORMAT = "d-m-Y"
SHORT_DATE_FORMAT = "d-m-Y"
DATETIME_FORMAT = "d-m-Y H:i"
SHORT_DATETIME_FORMAT = "d-m-Y H:i"
DATE_INPUT_FORMATS = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y"]
DATETIME_INPUT_FORMATS = ["%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M"]
FIRST_DAY_OF_WEEK = 1
