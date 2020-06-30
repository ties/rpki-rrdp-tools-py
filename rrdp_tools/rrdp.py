"""
https://tools.ietf.org/html/rfc8182
"""
from lxml.etree import RelaxNG

SCHEMA = RelaxNG.from_rnc_string("""#
# RELAX NG schema for the RPKI Repository Delta Protocol (RRDP).
#

default namespace = "http://www.ripe.net/rpki/rrdp"

version = xsd:positiveInteger   { maxInclusive="1" }
serial  = xsd:positiveInteger
uri     = xsd:anyURI
uuid    = xsd:string            { pattern = "[\-0-9a-fA-F]+" }
hash    = xsd:string            { pattern = "[0-9a-fA-F]+" }
base64  = xsd:base64Binary

# Notification File: lists current snapshots and deltas.

start |= element notification {
  attribute version    { version },
  attribute session_id { uuid },
  attribute serial     { serial },
  element snapshot {
    attribute uri  { uri },
    attribute hash { hash }
  },
  element delta {
    attribute serial { serial },
    attribute uri    { uri },
    attribute hash   { hash }
  }*
}

# Snapshot segment: think DNS AXFR.

start |= element snapshot {
  attribute version    { version },
  attribute session_id { uuid },
  attribute serial     { serial },
  element publish      {
    attribute uri { uri },
    base64
  }*
}

# Delta segment: think DNS IXFR.

start |= element delta {
 attribute version    { version },
 attribute session_id { uuid },
 attribute serial     { serial },
 delta_element+
}

delta_element |= element publish  {
 attribute uri  { uri },
 attribute hash { hash }?,
 base64
}

delta_element |= element withdraw {
 attribute uri  { uri },
 attribute hash { hash }
}

# Local Variables:
# indent-tabs-mode: nil
# comment-start: "# "
# comment-start-skip: "#[ \\t]*"
# End:
""")


def validate(doc) -> None:
    SCHEMA.assertValid(doc)
