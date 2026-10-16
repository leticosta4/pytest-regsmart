import textwrap

PLUGIN_HELP = textwrap.dedent("""\
Run regression test prioritization for pytest test suite.
It re-orders execution of tests to expose test failure sooner.
""")

WEIGHT_HELP = textwrap.dedent("""\
Set weights on different prioritization heuristics,
separated by hyphens `-`.
The sum of weights will be normalized to 1.
Higher weight means that heuristic will be favored.
Default value is 1-0.
""")

HIST_LEN_HELP = textwrap.dedent("""\
The maximum number of previous test runs
that can be recorded for a test since the test has failed.
Default value is 50 (must be integer).
""")

SEED_HELP = textwrap.dedent("""\
Seed when running tests in random order.
You can run random order via setting `--ranking-weight=0-0`
Default value is 0.
""")

RANK_LEVEL_HELP = textwrap.dedent("""
The test group level at which the prioritization takes place.
Test items below the configured level follow pytest default order.
Score of a test group is the mean score over all tests in that group.
Default value is PUT.
""")

REPLAY_HELP = textwrap.dedent("""
Provide a text file where each line is a test ID.
pytest-regsmart will run tests with the order defined in the file.  
Default value is None.
""")  ## gotta see what to do about this

NO_RANK_HELP = textwrap.dedent("""
Boolean flag to disable ranking option (RTP); cannot be used with other ranking flags.
When selected, tests will run in pytest default order.
""") #need to adapt this ending to use the RTS later

DIFF_LEVEL_HELP = textwrap.dedent("""
The levels at which the diff will be identified using Git and the level for the dependency graph.
Possible values are: file and function (default).
""")

LOCAL_DIFF_HELP = textwrap.dedent("""
Boolean flag to select tests from the local, uncommitted changes instead of the committed diff.
By default the diff is the changes committed between the merge base and HEAD (what CI checks out),
so build steps that rewrite files on disk do not leak into the selection.
Use this flag, or `local_diff = true` in pytest.ini, when running locally on changes you have not committed yet.
""")
