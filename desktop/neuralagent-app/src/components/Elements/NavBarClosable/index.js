import React from 'react';
import {
  ClosableContainer,
  ClosableText,
} from './NavBarClosableElements';
import { IconButton } from '../Button';
import { MdOutlineArrowBack, MdOutlineArrowForward } from 'react-icons/md';
import { useSelector } from 'react-redux';

const NavBarClosable = ({
  onCloseButtonClick,
  text,
  style=null
}) => {

  const isRTL = useSelector(state => state.isRTL);

  return (
    <>
      <ClosableContainer style={style}>
        <IconButton onClick={onCloseButtonClick}>
          {
            isRTL ? 
            <MdOutlineArrowForward /> :
            <MdOutlineArrowBack />
          }
        </IconButton>
        <ClosableText>
          {text}
        </ClosableText>
      </ClosableContainer>
    </>
  );
};

export default NavBarClosable;
