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
You can run random order via setting `--rank-weight=0-0`
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
The levels at which the diff will be identified using Git.
Default value is file, which means that the diff will be identified at the file level.
If you want to identify the diff at the function level, you can set this option to function.
""") #make this better asap
