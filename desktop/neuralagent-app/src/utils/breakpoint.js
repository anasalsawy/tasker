const size = {
  xs: '600px',
  sm: '960px',
  md: '1264px',
  lg: '1904px',
};

const int_size = {
  xs: 600,
  sm: 960,
  md: 1264,
  lg: 1904,
};

const checkers = {
  xsOnly: () => {
    return window.innerWidth <= int_size.xs;
  },
  smAndDown: () => {
    return window.innerWidth <= int_size.sm;
  },
  smAndUp: () => {
    return window.innerWidth > int_size.xs;
  },
  mdAndDown: () => {
    return window.innerWidth <= int_size.md;
  },
  mdAndUp: () => {
    return window.innerWidth >= int_size.md;
  },
  lgAndUp: () => {
    return window.innerWidth >= int_size.lg;
  },
  getFlexWidth (col) {
    if (col === 1) {
      return '8.33333333333333%';
    } else if (col === 2) {
      return '16.66666666666666%';
    } else if (col === 3) {
      return '25%';
    } else if (col === 4) {
      return '33.33333333333333%';
    } else if (col === 5) {
      return '41.66666666666666%';
    } else if (col === 6) {
      return '50%';
    } else if (col === 7) {
      return '58.33333333333333%';
    } else if (col === 8) {
      return '66.66666666666666%';
    } else if (col === 9) {
      return '75%';
    } else if (col === 10) {
      return '83.33333333333333%';
    } else if (col === 11) {
      return '91.66666666666666%';
    } else if (col === 12) {
      return '100%';
    }
  }
};

const breakpoint = {
  size: size,
  devices_max: {
    xs: `max-width: ${size.xs}`,
    sm: `max-width: ${size.sm}`,
    md: `max-width: ${size.md}`,
    lg: `max-width: ${size.lg}`,
  },
  devices_min: {
    xs: `min-width: ${size.xs}`,
    sm: `min-width: ${size.sm}`,
    md: `min-width: ${size.md}`,
    lg: `min-width: ${size.lg}`,
  },
  checkers: checkers,
}

export default breakpoint;