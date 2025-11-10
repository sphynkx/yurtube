from typing import Dict, Any, List


def collapse_children(children: List[str], limit: int) -> Dict[str, Any]:
    if len(children) <= limit:
        return {"visible": children, "collapsed": []}
    return {"visible": children[:limit], "collapsed": children[limit:]}