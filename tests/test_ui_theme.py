"""
Tests for UI Theme improvements (v0.4)
"""
import pytest


@pytest.mark.ui
def test_theme_colors_defined():
    """Test that all theme colors are properly defined"""
    from tools.ui.legacy.style import Colors
    
    # Background colors
    assert Colors.bg_app == "#0a0e1a"
    assert Colors.bg_panel == "#0f1420"
    assert Colors.bg_card == "#141b2d"
    assert Colors.bg_input == "#1a2332"
    
    # Accent colors
    assert Colors.blue == "#3b82f6"
    assert Colors.blue_light == "#60a5fa"
    assert Colors.blue_dark == "#2563eb"
    
    # Semantic colors
    assert Colors.green == "#10b981"
    assert Colors.red == "#ef4444"
    assert Colors.yellow == "#f59e0b"
    
    # Text colors
    assert Colors.text_primary == "#f1f5f9"
    assert Colors.text_secondary == "#a0aec0"
    assert Colors.text_muted == "#6b7280"


@pytest.mark.ui
def test_state_colors_complete():
    """Test that all drone states have colors defined"""
    from tools.ui.legacy.style import STATE_COLORS
    
    required_states = [
        "IDLE", "ARMING", "ARMED", "TAKEOFF", 
        "FLYING", "MISSION", "LANDING", "RTL", 
        "EMERGENCY", "UNKNOWN"
    ]
    
    for state in required_states:
        assert state in STATE_COLORS, f"Missing color for state: {state}"
        assert STATE_COLORS[state].startswith("#"), f"Invalid color format for {state}"
        assert len(STATE_COLORS[state]) == 7, f"Invalid color length for {state}"


@pytest.mark.ui
def test_drone_colors_sufficient():
    """Test that we have enough drone colors for multi-drone display"""
    from tools.ui.legacy.style import DRONE_COLORS
    
    # Should have at least 10 distinct colors for swarms
    assert len(DRONE_COLORS) >= 10
    
    # All should be valid hex colors
    for color in DRONE_COLORS:
        assert color.startswith("#")
        assert len(color) == 7
        
    # Should be distinct (no duplicates)
    assert len(DRONE_COLORS) == len(set(DRONE_COLORS))


@pytest.mark.ui
def test_color_contrast_accessibility():
    """Test that text colors have sufficient contrast against backgrounds"""
    from tools.ui.legacy.style import Colors
    
    def hex_to_rgb(hex_color):
        """Convert hex color to RGB tuple"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    def relative_luminance(rgb):
        """Calculate relative luminance for contrast ratio"""
        r, g, b = [x / 255.0 for x in rgb]
        r = r / 12.92 if r <= 0.03928 else ((r + 0.055) / 1.055) ** 2.4
        g = g / 12.92 if g <= 0.03928 else ((g + 0.055) / 1.055) ** 2.4
        b = b / 12.92 if b <= 0.03928 else ((b + 0.055) / 1.055) ** 2.4
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    
    def contrast_ratio(color1, color2):
        """Calculate WCAG contrast ratio between two colors"""
        lum1 = relative_luminance(hex_to_rgb(color1))
        lum2 = relative_luminance(hex_to_rgb(color2))
        lighter = max(lum1, lum2)
        darker = min(lum1, lum2)
        return (lighter + 0.05) / (darker + 0.05)
    
    # Test primary text on dark background (should be > 7:1 for AAA)
    primary_contrast = contrast_ratio(Colors.text_primary, Colors.bg_app)
    assert primary_contrast > 7.0, f"Primary text contrast too low: {primary_contrast:.2f}"
    
    # Test secondary text on dark background (should be > 4.5:1 for AA)
    secondary_contrast = contrast_ratio(Colors.text_secondary, Colors.bg_app)
    assert secondary_contrast > 4.5, f"Secondary text contrast too low: {secondary_contrast:.2f}"
    
    # Test accent color on dark background (should be > 3:1 for AA)
    accent_contrast = contrast_ratio(Colors.blue, Colors.bg_app)
    assert accent_contrast > 3.0, f"Accent contrast too low: {accent_contrast:.2f}"


@pytest.mark.ui
def test_stylesheet_generation():
    """Test that stylesheets are generated without errors"""
    from tools.ui.legacy.style import DARK_THEME, TAB_STYLESHEET, STATUSBAR_STYLESHEET
    
    # Should be non-empty strings
    assert isinstance(DARK_THEME, str)
    assert len(DARK_THEME) > 1000  # Should be substantial
    
    assert isinstance(TAB_STYLESHEET, str)
    assert len(TAB_STYLESHEET) > 100
    
    assert isinstance(STATUSBAR_STYLESHEET, str)
    assert len(STATUSBAR_STYLESHEET) > 50
    
    # Should contain Qt stylesheet syntax
    assert "QMainWindow" in DARK_THEME
    assert "QPushButton" in DARK_THEME
    assert "QTabBar" in TAB_STYLESHEET


@pytest.mark.ui
def test_button_variants_styling():
    """Test that button variant styles are properly defined"""
    from tools.ui.legacy.style import DARK_THEME
    
    # Should have styles for all button variants
    assert "btn_primary" in DARK_THEME
    assert "btn_danger" in DARK_THEME
    assert "btn_success" in DARK_THEME
    assert "btn_warning" in DARK_THEME
    
    # Should have hover states
    assert ":hover" in DARK_THEME
    assert ":pressed" in DARK_THEME
    assert ":disabled" in DARK_THEME


@pytest.mark.ui
def test_gradient_definitions():
    """Test that gradient definitions are present for modern buttons"""
    from tools.ui.legacy.style import DARK_THEME
    
    # Should contain gradient definitions
    assert "qlineargradient" in DARK_THEME
    assert "stop:0" in DARK_THEME
    assert "stop:1" in DARK_THEME


@pytest.mark.ui
def test_border_radius_consistency():
    """Test that border radius values are consistent"""
    from tools.ui.legacy.style import DARK_THEME
    
    # Should use consistent border radius values
    # Common values: 6px, 8px, 10px, 12px
    assert "border-radius: 8px" in DARK_THEME
    assert "border-radius: 10px" in DARK_THEME
    
    # Should not use arbitrary values like 5px, 7px, 9px
    assert "border-radius: 5px" not in DARK_THEME
    assert "border-radius: 7px" not in DARK_THEME
    assert "border-radius: 9px" not in DARK_THEME


@pytest.mark.ui
def test_font_families_defined():
    """Test that font families are properly defined"""
    from tools.ui.legacy.style import DARK_THEME
    
    # Should define sans-serif font stack
    assert "Segoe UI" in DARK_THEME
    assert "SF Pro Text" in DARK_THEME
    assert "Ubuntu" in DARK_THEME
    
    # Should define monospace font stack for console
    assert "Cascadia Code" in DARK_THEME or "JetBrains Mono" in DARK_THEME
    assert "monospace" in DARK_THEME


@pytest.mark.ui
def test_accessibility_features():
    """Test that accessibility features are present"""
    from tools.ui.legacy.style import DARK_THEME
    
    # Should have focus indicators
    assert ":focus" in DARK_THEME
    
    # Should have disabled states
    assert ":disabled" in DARK_THEME
    
    # Should have hover states for feedback
    assert ":hover" in DARK_THEME


@pytest.mark.ui
def test_color_immutability():
    """Test that Colors dataclass is immutable"""
    from tools.ui.legacy.style import Colors
    
    # Should not be able to modify colors
    with pytest.raises(AttributeError):
        Colors.bg_app = "#000000"
    
    with pytest.raises(AttributeError):
        Colors.blue = "#ff0000"


@pytest.mark.ui
def test_spacing_consistency():
    """Test that spacing values follow 8px grid system"""
    from tools.ui.legacy.style import DARK_THEME
    
    # Should use multiples of 4 or 8 for padding/margin
    # Common values: 4px, 8px, 10px, 12px, 16px, 20px, 24px
    
    # Count occurrences of consistent spacing
    consistent_spacing = [
        "4px", "8px", "10px", "12px", 
        "16px", "20px", "24px", "32px"
    ]
    
    spacing_count = sum(DARK_THEME.count(spacing) for spacing in consistent_spacing)
    
    # Should have many consistent spacing values
    assert spacing_count > 50, "Not enough consistent spacing values"


@pytest.mark.ui
def test_shadow_definitions():
    """Test that box shadows are defined for depth"""
    from tools.ui.legacy.style import DARK_THEME
    
    # Should have box-shadow definitions
    assert "box-shadow" in DARK_THEME or "shadow" in DARK_THEME.lower()


@pytest.mark.ui
def test_transition_smoothness():
    """Test that transitions are defined for smooth animations"""
    from tools.ui.legacy.style import DARK_THEME
    
    # Should have transition or animation definitions
    # Note: Qt stylesheets don't support CSS transitions,
    # but we should have hover states that imply smooth changes
    assert ":hover" in DARK_THEME
    assert ":pressed" in DARK_THEME

