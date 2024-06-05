# ----------------------------------------------------------------------
#
#    Dockerfile script -- This file is part of the Shoestring AWS Relay 
#
#    Copyright (C) 2022  Shoestring and University of Cambridge
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License as published by
#    the Free Software Foundation, version 3 of the License.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see https://www.gnu.org/licenses/.
#
# ----------------------------------------------------------------------

FROM digitalshoestring/shoestring-aws-relay:v1.0.0

COPY ./requirements.txt /
RUN pip3 install -r requirements.txt
WORKDIR /app
ADD ./code/ /app

CMD [ "python3", "/app/main.py"]
