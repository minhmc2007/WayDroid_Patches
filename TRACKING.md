Waydroid-ATV fork tracking vs LineageOS lineage-22.2
====================================================================================================
project                       status     ahead behind  files  patches   action
----------------------------------------------------------------------------------------------------
frameworks/av                 diverged      27     10     54       27   ok (diverged, 10 LOS commit(s) not in fork)
frameworks/base               diverged      15    105     17       15   ok (diverged, 105 LOS commit(s) not in fork)
frameworks/native             diverged      11      3     18       11   ok (diverged, 3 LOS commit(s) not in fork)
lineage-sdk                   diverged       8      7     20        8   ok (diverged, 7 LOS commit(s) not in fork)
packages/apps/TvSettings      behind         0      2      0        0   nothing to do (fork has no commits we lack)
system/core                   diverged      18      1     14       18   ok (diverged, 1 LOS commit(s) not in fork)

Synced (never patched, plain repo projects): 22 entries in manifest/10-waydroid-projects.xml

Fork set is 5, not 7: system/vold and hardware/interfaces are not forks on
22.2. Upstream ships them verbatim, so they are layer 20 patches instead.
