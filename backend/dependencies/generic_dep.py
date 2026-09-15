# from fastapi import Header, HTTPException
#
# async def get_header_value(header_value: str = Header(None, alias="X-Your-Header")):
#     """
#     Dependency to retrieve a specific header value.
#     :param header_value: Value of the header retrieved from the request.
#     :return: The header value if valid.
#     """
#     if header_value is None:
#         raise HTTPException(
#             status_code=400, detail="Missing required header: X-Your-Header"
#         )
#     # Optional: Apply transformations or validation here
#     if len(header_value) < 5:  # Example validation
#         raise HTTPException(
#             status_code=422,
#             detail="The header 'X-Your-Header' must be at least 5 characters long.",
#         )
#     return header_value