**Added:**

* Added ``system.electrochemicalCell.parts``: the functional parts of the cell in contact with or close to an electrolyte (``name``, ``description``, ``comment``), each listing what it is made of in ``components`` (``name``, ``material``, ``description``, ``source`` with ``manufacturer`` and ``supplier``), so that a part made of several materials, such as a degasser of a glass tube and a Nafion membrane, can be described. (#128)
* Added ``contact`` to each cell component, listing the names of the entries of ``system.electrolytes`` the component is in contact with; it is omitted for components close to but not in contact with an electrolyte, such as a clamp holding an electrode. ``mdstools`` checks that these names exist. (#128, #129)

**Changed:**

* Changed the flat list ``system.electrochemicalCell.components`` of ``{name, part, description}`` to ``system.electrochemicalCell.parts``. This is a breaking change; run ``mdstools update`` to migrate existing files, which turns each old entry into a part named after its ``part``, with one component named after its ``name``; add the ``material`` of each component where known. (#128)

**Removed:**

* Removed ``system.electrochemicalCell.components``; existing files are upgraded by the migration. (#128)
